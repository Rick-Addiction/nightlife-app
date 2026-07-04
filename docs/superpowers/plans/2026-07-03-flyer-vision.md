# Nightlife App — Plano G: Vision extractor de flyers (backend Codex) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar imagens de flyer (inbox `flyers/`) em `RawEvent`s pelo pipeline existente — extração via `codex exec` (assinatura, custo marginal zero) atrás de uma interface plugável, com contrato anti-alucinação, dHash para dedupe por conteúdo e proteção de cota.

**Architecture:** Spec: `docs/superpowers/specs/2026-07-03-flyer-vision-design.md`. Camadas puras (`extraction/imagehash.py`, `extraction/flyer.py`) testadas offline; `CodexExtractor` com runner injetável (testes não gastam cota); `FlyerSource` implementa `Source`; pipeline ganha ancoragem por `venue_name` (ancora venue existente, nunca cria). Smoke real no final calibra os flags do `codex exec`.

**Tech Stack:** Python 3.14 · Pillow (dHash) · Pydantic (validação do contrato) · subprocess (codex exec) · pytest. Postgres na 5434 (Docker).

**Convenções:**
- `.venv/Scripts/python -m ...`; cwd RESETA entre chamadas Bash — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Testes de DB: `docker compose up -d --wait`. Contagem: `-o console_output_style=count -p no:warnings` (sem pipe pra grep/tail).
- Suíte atual: **90 passed**. Commits terminam com: `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`
- **NÃO modifique** `config.py`, `docker-compose.yml`, `tests/conftest.py`, `migrations/`, `models.py`, `api/`, repos de persistência.
- Os testes NÃO invocam o `codex` real (runner fake injetado) — só o smoke da Task 5 gasta ~2 execuções.

---

## File Structure

```
src/nightlife/
  extraction/
    imagehash.py         # dhash puro (Pillow)  (Task 0)
    flyer.py             # FlyerExtraction + Protocol + flyer_to_raw_event  (Task 1)
  ingestion/
    base.py              # RawEvent + venue_name, lineup_text  (Task 2)
    pipeline.py          # ancoragem por venue_name  (Task 2)
    codex_extractor.py   # CodexExtractor (subprocess, runner injetável)  (Task 3)
    flyer_source.py      # FlyerSource  (Task 4)
  ingest_flyers.py       # runner  (Task 5)
tests/
  test_imagehash.py (T0) · test_flyer.py (T1) · test_pipeline.py (T2, append)
  test_codex_extractor.py (T3) · test_flyer_source.py (T4)
pyproject.toml (T0: pillow) · README.md (T5)
```

---

## Task 0: dHash puro (`extraction/imagehash.py`)

**Files:**
- Modify: `pyproject.toml` (adicionar `"pillow>=10.0",` ao bloco `dependencies`, após `"truststore>=0.9",`)
- Create: `src/nightlife/extraction/imagehash.py`
- Test: `tests/test_imagehash.py`

- [ ] **Step 1: Instalar a dep**

Edite `pyproject.toml` (linha nova no `dependencies`) e rode:
`cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pip install -e ".[dev]"`
Expected: instala `pillow` sem erro (wheels CP314 existem).

- [ ] **Step 2: Teste que falha** — create `tests/test_imagehash.py`:

```python
# tests/test_imagehash.py
from PIL import Image

from nightlife.extraction.imagehash import dhash


def _gradient(path, size=(160, 120), reverse=False):
    img = Image.new("L", size)
    w = size[0]
    img.putdata([
        (255 - (x * 255 // w)) if reverse else (x * 255 // w)
        for _ in range(size[1]) for x in range(w)
    ])
    img.save(path)
    return path


def test_same_content_same_hash_even_resized(tmp_path):
    a = _gradient(tmp_path / "a.png")
    h1 = dhash(a)
    # mesma imagem redimensionada (como um repost/screenshot) -> mesmo hash
    with Image.open(a) as img:
        img.resize((320, 240)).save(tmp_path / "b.png")
    assert dhash(tmp_path / "b.png") == h1
    assert len(h1) == 16  # 64 bits em hex


def test_different_content_different_hash(tmp_path):
    a = _gradient(tmp_path / "a.png")
    b = _gradient(tmp_path / "b.png", reverse=True)
    assert dhash(a) != dhash(b)
```

- [ ] **Step 3: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_imagehash.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.extraction.imagehash'`.

- [ ] **Step 4: Implementar** — create `src/nightlife/extraction/imagehash.py`:

```python
# src/nightlife/extraction/imagehash.py
from __future__ import annotations

from pathlib import Path

from PIL import Image


def dhash(image_path: Path | str) -> str:
    """Difference hash (64 bits, hex) — identifica o CONTEUDO da imagem.

    Robusto a redimensionamento/recompressao (repost do mesmo flyer);
    imagens diferentes divergem. Puro dado o arquivo; sem scipy/imagehash.
    """
    with Image.open(image_path) as img:
        small = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        px = list(small.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            left = px[row * 9 + col]
            right = px[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"
```

- [ ] **Step 5: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_imagehash.py -q`
Expected: PASS (2). Suíte inteira: **92**.

```bash
cd /d/MyProjects/nightlife-app && git add pyproject.toml src/nightlife/extraction/imagehash.py tests/test_imagehash.py && git commit -m "feat(extraction): dhash de imagem (dedupe de flyer por conteudo)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 1: Contrato de extração (`extraction/flyer.py`)

**Files:**
- Create: `src/nightlife/extraction/flyer.py`
- Test: `tests/test_flyer.py`

- [ ] **Step 1: Teste que falha** — create `tests/test_flyer.py`:

```python
# tests/test_flyer.py
from datetime import date

from nightlife.extraction.flyer import FlyerExtraction, flyer_to_raw_event

REF = date(2026, 6, 1)

GOOD = {
    "event_name": "MAMBA NEGRA",
    "date_text": "SEX 13/06 23h",
    "venue_name": "Lab Club",
    "organizer": "Mamba Org",
    "lineup": ["DJ A", "DJ B"],
    "price_text": "R$ 60",
    "ticket_url": "https://shotgun.live/mamba",
    "instagram_handle": "@mambanegra",
    "quotes": {"event_name": "MAMBA NEGRA", "date_text": "SEX 13/06 23h",
               "venue_name": "LAB CLUB", "organizer": "por MAMBA",
               "ticket_url": "shotgun.live/mamba"},
    "confidence": {"event_name": 0.95, "date_text": 0.9, "venue_name": 0.9,
                   "organizer": 0.6, "ticket_url": 0.8},
}


def test_adjusted_confidence_halves_fields_without_quote():
    ext = FlyerExtraction.model_validate({
        **GOOD,
        "quotes": {"event_name": "MAMBA NEGRA"},  # so event_name tem quote
    })
    adj = ext.adjusted_confidence()
    assert adj["event_name"] == 0.95          # com quote: intacto
    assert adj["date_text"] == 0.45           # sem quote: cortado pela metade
    assert adj["venue_name"] == 0.45


def test_flyer_to_raw_event_maps_and_parses_date():
    ext = FlyerExtraction.model_validate(GOOD)
    rev = flyer_to_raw_event(ext, "abc123", reference=REF)
    assert rev is not None
    assert rev.name == "MAMBA NEGRA"
    assert rev.source_type == "vision_flyer"
    # data parseada pelo NOSSO dates_ptbr, nao pelo modelo
    assert rev.starts_at is not None
    assert (rev.starts_at.day, rev.starts_at.hour) == (13, 23)
    assert rev.venue_name == "Lab Club" and rev.venue is None  # ancora, nao cria
    assert rev.organizer_name == "Mamba Org"
    assert rev.lineup_text == "DJ A, DJ B"
    assert rev.ticket_url == "https://shotgun.live/mamba"
    assert rev.source_url == "flyer:abc123"


def test_flyer_to_raw_event_guards():
    # sem event_name -> nao vira evento
    ext = FlyerExtraction.model_validate({**GOOD, "event_name": None})
    assert flyer_to_raw_event(ext, "x", reference=REF) is None
    # link generico (linktree) NAO vira ticket_url (quebraria o dedupe)
    ext2 = FlyerExtraction.model_validate({**GOOD, "ticket_url": "https://linktr.ee/clubx"})
    rev2 = flyer_to_raw_event(ext2, "x", reference=REF)
    assert rev2.ticket_url is None
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_flyer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.extraction.flyer'`.

- [ ] **Step 3: Implementar** — create `src/nightlife/extraction/flyer.py`:

```python
# src/nightlife/extraction/flyer.py
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from ..domain.dates_ptbr import parse_ptbr_datetime
from ..ingestion.base import RawEvent
from .freetext import _clean_url, _is_generic_link


class FlyerExtraction(BaseModel):
    """Contrato anti-alucinacao (spec §4): null p/ ausente, quotes como evidencia."""

    event_name: str | None = None
    date_text: str | None = None       # texto CRU do flyer; quem converte e o dates_ptbr
    venue_name: str | None = None
    organizer: str | None = None
    lineup: list[str] = Field(default_factory=list)
    price_text: str | None = None
    ticket_url: str | None = None
    instagram_handle: str | None = None
    quotes: dict[str, str] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)

    def adjusted_confidence(self) -> dict[str, float]:
        """Campo preenchido sem quote que o sustente e suspeito: confianca cai pela metade."""
        return {
            field: (c if field in self.quotes else c / 2)
            for field, c in self.confidence.items()
        }


class FlyerExtractor(Protocol):
    def extract(self, image_path: Path) -> FlyerExtraction | None: ...


def flyer_to_raw_event(
    extraction: FlyerExtraction, image_hash: str, *, reference: date
) -> RawEvent | None:
    """Extracao validada -> RawEvent. Pura. Descarta se nao ha nome de evento."""
    if not extraction.event_name:
        return None

    starts = None
    if extraction.date_text:
        starts = parse_ptbr_datetime(extraction.date_text, reference=reference).dt

    ticket = None
    if extraction.ticket_url:
        url = _clean_url(extraction.ticket_url.strip())
        if url and not _is_generic_link(url):
            ticket = url

    return RawEvent(
        name=extraction.event_name,
        source_type="vision_flyer",
        starts_at=starts,
        venue_name=extraction.venue_name,   # ancora no catalogo; nunca cria venue
        organizer_name=extraction.organizer,
        lineup_text=", ".join(extraction.lineup) or None,
        ticket_url=ticket,
        source_url=f"flyer:{image_hash}",
        raw_payload=extraction.model_dump_json(),
    )
```

(Nota: `_clean_url`/`_is_generic_link` são privados de `extraction/freetext.py` — reuso interno do mesmo pacote, aceitável no esqueleto. Os campos `venue_name`/`lineup_text` do `RawEvent` chegam na Task 2 — por isso a Task 2 roda ANTES da suíte inteira ficar verde; nesta task rode só `tests/test_flyer.py` após a Task 2, OU siga a ordem: Task 2 primeiro se preferir. ORDEM RECOMENDADA DE EXECUÇÃO: T0 → **T2** → T1 → T3 → T4 → T5.)

- [ ] **Step 4: Ver passar + commit** (após T2 existir)

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_flyer.py -q`
Expected: PASS (3).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/extraction/flyer.py tests/test_flyer.py && git commit -m "feat(extraction): contrato de extracao de flyer (anti-alucinacao + data via dates_ptbr)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: `RawEvent.venue_name`/`lineup_text` + ancoragem no pipeline

> **Executar ANTES da Task 1** (ela importa os campos novos). Ordem: T0 → T2 → T1 → T3 → T4 → T5.

**Files:**
- Modify: `src/nightlife/ingestion/base.py` (2 campos), `src/nightlife/ingestion/pipeline.py` (2 pontos)
- Test: `tests/test_pipeline.py` (append)

- [ ] **Step 1: Teste que falha** — append em `tests/test_pipeline.py`:

```python
def test_pipeline_anchors_by_venue_name_without_creating(session):
    from datetime import datetime, timezone

    from nightlife.ingestion.base import RawEvent

    v = Venue(name="Lab Club")
    session.add(v)
    session.flush()

    known = RawEvent(name="Festa do Flyer", source_type="vision_flyer",
                     starts_at=datetime(2099, 6, 14, 2, 0, tzinfo=timezone.utc),
                     venue_name="Lab Club", lineup_text="DJ A, DJ B")
    unknown = RawEvent(name="Festa Misteriosa", source_type="vision_flyer",
                       starts_at=datetime(2099, 7, 14, 2, 0, tzinfo=timezone.utc),
                       venue_name="Clube Que Nao Existe Xyz")
    run_ingestion(session, MockSource([], [], events=[known, unknown]), reference=REF)
    session.flush()

    assert len(session.scalars(select(Venue)).all()) == 1  # NAO criou venue novo
    events = {e.name: e for e in session.scalars(select(Event)).all()}
    assert events["Festa do Flyer"].venue_id == v.id       # ancorou por nome
    assert events["Festa do Flyer"].lineup_text == "DJ A, DJ B"
    assert events["Festa Misteriosa"].venue_id is None     # desconhecido: sem venue
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_pipeline.py -q`
Expected: FAIL — `TypeError: RawEvent.__init__() got an unexpected keyword argument 'venue_name'`.

- [ ] **Step 3: Implementar**

Em `src/nightlife/ingestion/base.py`, no dataclass `RawEvent`, logo após `venue: RawVenue | None = None`, adicione:

```python
    venue_name: str | None = None       # so ANCORA em venue existente (flyer: nome sem geo)
    lineup_text: str | None = None
```

Em `src/nightlife/ingestion/pipeline.py`, no loop `for rev in raw_events:`:

1. No bloco `venue = None / if rev.venue is not None: venue = upsert_venue(...)`, adicione um ramo `elif` logo APÓS a linha `)` que fecha a chamada de `upsert_venue` (mesma indentação do `if`):
```python
            elif rev.venue_name:
                # flyer da nome sem geo (e com typo): ancora no catalogo, nunca cria
                venue = _resolve_venue(session, rev.venue_name)
```

2. No `EventInput(...)` desse loop, substitua a linha:
```python
                    venue_name=rev.venue.name if rev.venue is not None else None,
```
por:
```python
                    venue_name=rev.venue.name if rev.venue is not None else rev.venue_name,
```
e adicione, após a linha `genre=rev.genre, ticket_url=rev.ticket_url,`:
```python
                    lineup_text=rev.lineup_text,
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_pipeline.py -q`
Expected: PASS (8 no arquivo). Suíte inteira: **93** (92 + 1).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/base.py src/nightlife/ingestion/pipeline.py tests/test_pipeline.py && git commit -m "feat(ingestion): RawEvent.venue_name ancora venue existente sem criar (+ lineup_text)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: `CodexExtractor` (runner injetável)

**Files:**
- Create: `src/nightlife/ingestion/codex_extractor.py`
- Test: `tests/test_codex_extractor.py`

- [ ] **Step 1: Teste que falha** — create `tests/test_codex_extractor.py`:

```python
# tests/test_codex_extractor.py
import json
from pathlib import Path

from nightlife.ingestion.codex_extractor import CodexExtractor

GOOD_JSON = json.dumps({
    "event_name": "MAMBA NEGRA", "date_text": "SEX 13/06 23h",
    "venue_name": "Lab Club", "organizer": None, "lineup": [],
    "price_text": None, "ticket_url": None, "instagram_handle": None,
    "quotes": {"event_name": "MAMBA NEGRA"}, "confidence": {"event_name": 0.9},
})


def test_extracts_from_wrapped_output(tmp_path):
    # CLIs de agente cercam o JSON de logs/preambulo: extrair do 1o { ao ultimo }
    calls = []

    def fake_runner(image_path, prompt):
        calls.append(prompt)
        return f"thinking...\nsegue o resultado:\n{GOOD_JSON}\nfim."

    ext = CodexExtractor(runner=fake_runner)
    result = ext.extract(tmp_path / "flyer.png")
    assert result is not None and result.event_name == "MAMBA NEGRA"
    assert len(calls) == 1


def test_retry_once_on_invalid_then_success(tmp_path):
    outputs = ["isso nao e json", GOOD_JSON]
    calls = []

    def fake_runner(image_path, prompt):
        calls.append(prompt)
        return outputs[len(calls) - 1]

    result = CodexExtractor(runner=fake_runner).extract(tmp_path / "f.png")
    assert result is not None
    assert len(calls) == 2
    assert "invalida" in calls[1].lower()  # o retry anexa o motivo


def test_gives_up_after_retry(tmp_path):
    result = CodexExtractor(runner=lambda p, q: "lixo sem json").extract(tmp_path / "f.png")
    assert result is None
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_codex_extractor.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar** — create `src/nightlife/ingestion/codex_extractor.py`:

```python
# src/nightlife/ingestion/codex_extractor.py
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from ..extraction.flyer import FlyerExtraction

_log = logging.getLogger(__name__)

_PROMPT = """Voce esta lendo a IMAGEM de um flyer de festa/evento de Sao Paulo.
Extraia APENAS o que esta escrito no flyer e responda com UM UNICO objeto JSON,
sem markdown e sem texto antes ou depois, exatamente neste formato:

{"event_name": str|null, "date_text": str|null, "venue_name": str|null,
 "organizer": str|null, "lineup": [str], "price_text": str|null,
 "ticket_url": str|null, "instagram_handle": str|null,
 "quotes": {campo: trecho do flyer que sustenta o valor},
 "confidence": {campo: 0.0 a 1.0}}

Regras:
- Campo ausente no flyer = null. NUNCA invente valores.
- date_text: copie o texto da data EXATAMENTE como esta no flyer
  (ex: "SEX 13/06 23h"). Nao converta, nao interprete, nao calcule.
- quotes: para cada campo preenchido, o trecho do flyer que o sustenta.
- lineup: nomes dos artistas como escritos, na ordem do flyer."""


def _run_codex(image_path: Path, prompt: str) -> str:
    """Invoca o codex CLI em modo nao-interativo com a imagem anexada.

    Flags calibrados no smoke real (Task 5) — requisito: exec headless,
    imagem como input, resultado no stdout.
    """
    result = subprocess.run(
        ["codex", "exec", "--skip-git-repo-check", "-i", str(image_path), prompt],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300,
    )
    return result.stdout or ""


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("nenhum objeto JSON na saida")
    return json.loads(text[start:end + 1])


class CodexExtractor:
    """FlyerExtractor via codex exec (assinatura). Runner injetavel p/ testes."""

    def __init__(self, *, runner: Callable[[Path, str], str] | None = None,
                 retries: int = 1) -> None:
        self._runner = runner or _run_codex
        self._retries = retries

    def extract(self, image_path: Path) -> FlyerExtraction | None:
        prompt = _PROMPT
        for attempt in range(self._retries + 1):
            try:
                output = self._runner(image_path, prompt)
                data = _extract_json(output)
                return FlyerExtraction.model_validate(data)
            except (ValueError, json.JSONDecodeError, ValidationError,
                    subprocess.SubprocessError, OSError) as exc:
                _log.warning("extracao de %s falhou (tentativa %d): %s",
                             image_path, attempt + 1, exc)
                prompt = (_PROMPT + "\n\nATENCAO: sua resposta anterior foi invalida "
                          f"({exc}). Responda APENAS com o objeto JSON.")
        return None
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_codex_extractor.py -q`
Expected: PASS (3). Suíte inteira: **99** (93 + 3 do T1 + 3 daqui).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/codex_extractor.py tests/test_codex_extractor.py && git commit -m "feat(ingestion): CodexExtractor (codex exec headless, retry, runner injetavel)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 4: `FlyerSource`

**Files:**
- Create: `src/nightlife/ingestion/flyer_source.py`
- Test: `tests/test_flyer_source.py`

- [ ] **Step 1: Teste que falha** — create `tests/test_flyer_source.py`:

```python
# tests/test_flyer_source.py
import shutil
from datetime import date

from PIL import Image

from nightlife.extraction.flyer import FlyerExtraction
from nightlife.ingestion.flyer_source import FlyerSource

REF = date(2026, 6, 1)


def _img(path, seed=0):
    img = Image.new("L", (80, 60))
    img.putdata([(x * (seed + 1) + y) % 256 for y in range(60) for x in range(80)])
    img.save(path)
    return path


class _FakeExtractor:
    def __init__(self, results):
        self.results = results  # por nome de arquivo
        self.calls = []

    def extract(self, image_path):
        self.calls.append(image_path.name)
        return self.results.get(image_path.name)


def _extraction(name="Festa X"):
    return FlyerExtraction(event_name=name, date_text="13/06 23h",
                           quotes={"event_name": name}, confidence={"event_name": 0.9})


def test_scans_dedupes_and_tracks_paths(tmp_path):
    a = _img(tmp_path / "a.png", seed=1)
    _img(tmp_path / "b.png", seed=2)
    shutil.copy(a, tmp_path / "a_repost.png")   # mesmo conteudo, outro nome
    (tmp_path / "notas.txt").write_text("nao e imagem")

    fake = _FakeExtractor({"a.png": _extraction("Festa A"), "b.png": _extraction("Festa B")})
    src = FlyerSource(tmp_path, fake, reference=REF)
    events = src.events()

    assert sorted(fake.calls) == ["a.png", "b.png"]          # repost NAO gastou extracao
    assert sorted(e.name for e in events) == ["Festa A", "Festa B"]
    assert all(e.source_type == "vision_flyer" for e in events)
    assert sorted(p.name for p in src.processed_paths) == ["a.png", "a_repost.png", "b.png"]
    assert src.failed_paths == []
    assert src.venues() == [] and src.event_pages() == []


def test_failed_extraction_goes_to_failed(tmp_path):
    _img(tmp_path / "ruim.png", seed=3)
    fake = _FakeExtractor({})  # extractor devolve None
    src = FlyerSource(tmp_path, fake, reference=REF)
    assert src.events() == []
    assert [p.name for p in src.failed_paths] == ["ruim.png"]
    assert src.processed_paths == []
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_flyer_source.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar** — create `src/nightlife/ingestion/flyer_source.py`:

```python
# src/nightlife/ingestion/flyer_source.py
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from ..extraction.flyer import FlyerExtractor, flyer_to_raw_event
from ..extraction.imagehash import dhash
from .base import RawEvent, RawEventPage, RawVenue

_log = logging.getLogger(__name__)

_IMAGE_GLOBS = ("*.jpg", "*.jpeg", "*.png", "*.webp")


class FlyerSource:
    """Fonte de flyers: varre um inbox de imagens, extrai via FlyerExtractor.

    Expoe processed_paths (extraidos com sucesso + duplicatas por dHash) e
    failed_paths (extracao falhou ou sem nome de evento) para o runner mover —
    protecao de cota: imagem processada nunca e re-extraida.
    """

    def __init__(self, directory: Path | str, extractor: FlyerExtractor,
                 *, reference: date) -> None:
        self._dir = Path(directory)
        self._extractor = extractor
        self._reference = reference
        self.processed_paths: list[Path] = []
        self.failed_paths: list[Path] = []

    def venues(self) -> list[RawVenue]:
        return []

    def event_pages(self) -> list[RawEventPage]:
        return []

    def events(self) -> list[RawEvent]:
        self.processed_paths = []
        self.failed_paths = []
        out: list[RawEvent] = []
        seen_hashes: set[str] = set()

        images = sorted(p for g in _IMAGE_GLOBS for p in self._dir.glob(g))
        for path in images:
            image_hash = dhash(path)
            if image_hash in seen_hashes:
                self.processed_paths.append(path)  # duplicata: nao gasta extracao
                continue
            seen_hashes.add(image_hash)

            extraction = self._extractor.extract(path)
            raw_event = (flyer_to_raw_event(extraction, image_hash, reference=self._reference)
                         if extraction is not None else None)
            if raw_event is None:
                _log.warning("flyer %s: extracao falhou ou sem nome de evento", path.name)
                self.failed_paths.append(path)
                continue
            out.append(raw_event)
            self.processed_paths.append(path)
        return out
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_flyer_source.py -q`
Expected: PASS (2). Suíte inteira: **101**.

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/flyer_source.py tests/test_flyer_source.py && git commit -m "feat(ingestion): FlyerSource (inbox + dedupe por dhash + trilha de processados)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 5: Runner `ingest_flyers` + README + smoke REAL

**Files:**
- Create: `src/nightlife/ingest_flyers.py`
- Modify: `README.md`
- (Calibração, SE necessária: apenas `_run_codex` em `codex_extractor.py`)

- [ ] **Step 1: Criar o runner** — create `src/nightlife/ingest_flyers.py`:

```python
# src/nightlife/ingest_flyers.py
"""Ingere flyers do inbox flyers/ no banco (extracao via codex CLI).

Uso: coloque imagens em flyers/ e rode
  .venv/Scripts/python -m nightlife.ingest_flyers
Processadas vao para flyers/processed/; falhas para flyers/failed/.
"""
from __future__ import annotations

import shutil
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.codex_extractor import CodexExtractor
from .ingestion.flyer_source import FlyerSource
from .ingestion.pipeline import run_ingestion
from .models import Event

FLYERS_DIR = Path("flyers")


def _move_all(paths: list[Path], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for p in paths:
        target = dest / p.name
        if target.exists():
            target.unlink()
        shutil.move(str(p), str(target))


def main() -> None:
    if shutil.which("codex") is None:
        print("ERRO: codex CLI nao encontrado no PATH (instale/logue o Codex).")
        sys.exit(1)
    FLYERS_DIR.mkdir(exist_ok=True)

    source = FlyerSource(FLYERS_DIR, CodexExtractor(), reference=date.today())
    with SessionLocal() as session:
        run = run_ingestion(session, source, reference=date.today(), label="flyers")
        session.commit()
        events = session.scalar(select(func.count()).select_from(Event))
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"processadas={len(source.processed_paths)} "
              f"falhas={len(source.failed_paths)} | DB: {events} events")
        if run.errors:
            print("erros:\n" + run.errors[:2000])

    _move_all(source.processed_paths, FLYERS_DIR / "processed")
    _move_all(source.failed_paths, FLYERS_DIR / "failed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: README** — na seção "### Ingestão real", adicione ao bloco bash:

```bash
.venv/Scripts/python -m nightlife.ingest_flyers   # flyers do inbox flyers/ (visao via codex CLI)
```

E logo após o bloco, o parágrafo:

```markdown
Flyers: jogue imagens (print de story, download de post) em `flyers/` e rode o
runner — a extração usa o Codex CLI da sua assinatura (custo marginal zero).
Processadas vão para `flyers/processed/`, falhas para `flyers/failed/`
(nenhuma imagem é extraída duas vezes).
```

- [ ] **Step 3: Suíte inteira**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest -q -o console_output_style=count -p no:warnings`
Expected: **101 passed** (`[101/101]`).

- [ ] **Step 4: Smoke REAL** (gasta ~2 execuções de Codex; timeout Bash generoso, ex. 600000ms)

1. Primeiro calibre o comando isoladamente com um flyer sintético:
```bash
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -c "
from PIL import Image, ImageDraw
img = Image.new('RGB', (600, 800), '#111')
d = ImageDraw.Draw(img)
d.text((60, 100), 'MAMBA NEGRA', fill='#ff2266')
d.text((60, 200), 'SEX 13/03 23h', fill='white')
d.text((60, 300), 'LAB CLUB - Sao Paulo', fill='white')
d.text((60, 400), 'DJ A / DJ B / DJ C', fill='#aaa')
import pathlib; pathlib.Path('flyers').mkdir(exist_ok=True)
img.save('flyers/teste_mamba.png')
print('flyer sintetico criado')
"
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -c "
from pathlib import Path
from nightlife.ingestion.codex_extractor import CodexExtractor
r = CodexExtractor().extract(Path('flyers/teste_mamba.png'))
print(r)
"
```
Expected: imprime um `FlyerExtraction` com `event_name='MAMBA NEGRA'` (ou próximo). **Calibração permitida SÓ em `_run_codex`** (flags do CLI): se o comando falhar (flag inexistente, saída vazia), rode `codex exec --help`, ajuste os flags em `_run_codex` (ex.: forma de anexar imagem, flag de saída), e re-teste. NÃO altere prompt/validação/testes.

2. Depois o fluxo completo:
```bash
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m nightlife.ingest_flyers
```
Expected: `status=finished found=1 created=1`, imagem movida pra `flyers/processed/`, e o evento no banco (`Mamba Negra`... ancorado no venue "Lab Club" real do catálogo!). Rode o runner de novo (inbox vazio): `found=0`, nada gasto.

Se o codex falhar persistentemente (auth/quota), reporte a saída (DONE_WITH_CONCERNS) — não fique em loop.

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingest_flyers.py README.md src/nightlife/ingestion/codex_extractor.py && git commit -m "feat(ingestion): runner ingest_flyers + README (+calibracao de flags se houve)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Coverage map (Plano G ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §5 dHash puro (Pillow) | Task 0 |
| §4–5 contrato anti-alucinação + `flyer_to_raw_event` (data via dates_ptbr, quote→confidence, link genérico) | Task 1 |
| §6 `RawEvent.venue_name` + ancoragem sem criar venue (+ lineup_text) | Task 2 |
| §5 `CodexExtractor` (headless, retry, runner injetável) | Task 3 |
| §5, §7 `FlyerSource` (inbox, dedupe intra-lote, trilhas processed/failed) | Task 4 |
| §2, §7–8 runner com move-to-processed + smoke real + calibração de flags | Task 5 |
| §9 pillow dep; codex como dependência de máquina com erro claro | Tasks 0, 5 |

**Fora deste plano:** backends alternativos (Claude API/headless), endpoint de upload, monitoramento de IG — futuros.
