# Ciclo E-1: Intérprete de Posts + Catálogo Denso — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Post do IG vira documento INTERPRETADO (imagem + legenda + contexto do venue → ações add 1..N / cancel / update / ignore com anti-alucinação por ação); evento sem data fica visível como DATA A CONFIRMAR; cancelado some do default; catálogo ganha `add_place` (Text Search pontual) e re-varredura densa por célula.

**Architecture:** Spec `docs/superpowers/specs/2026-07-11-e1-interprete-posts-design.md`. Novo caminho de ingestão IG: `Document` → `PostInterpreter` (codex, runner injetável) → `sanitize_actions` (puro) → `ActionExecutor` (persistência: upsert/cancel/update/log) → orquestrado por `post_flow.process_inbox` (dHash, sidecars, processed/failed, IngestionRun), consumido por `ingest_flyers` e `sweep_area`. O caminho antigo (`FlyerSource`/`FlyerExtraction`/`flyer_to_raw_event`/`CodexExtractor`) SAI ao final, com testes SUBSTITUÍDOS. A plomberia do codex CLI (Windows shims, stdin, imagem sanitizada) é PROMOVIDA a módulo compartilhado — não reescreva, mova.

**Tech Stack:** Python 3.14 + pydantic v2 + SQLAlchemy 2 + pytest; codex CLI (assinatura); React 19 + TS + Vitest; Google Places API New (Text Search).

**Referências verificadas do código atual (2026-07-11, branch `feat/e1-interprete-posts`):**
- `ingestion/codex_extractor.py`: `_run_codex(image_path, prompt)` (TODAS as lições de Windows/segurança no docstring — PRESERVAR), `_extract_json(text)`, `CodexExtractor(runner=..., retries=1)` com retry re-prompt. `_PROMPT` atual é 1-evento.
- `extraction/flyer.py`: `FlyerExtraction` (quotes/confidence + `adjusted_confidence` — campo sem quote cai pela metade) e `flyer_to_raw_event` (gate 0.5; date via `parse_ptbr_datetime(text, reference=...)` → `.dt`; `_clean_url`/`_is_generic_link` de `extraction/freetext.py` p/ ticket_url).
- `ingestion/flyer_source.py::FlyerSource.events()`: glob de imagens, dHash dedupe (`extraction/imagehash.dhash`), sidecar `{caption, permalink, handle}`, `processed_paths`/`failed_paths` (mover é responsabilidade do caller).
- `ingest_flyers.py`: `move_all(paths, dest)` público (renomeado no D-1); cria `IngestionRun` via `run_ingestion(label="flyers")`.
- `sweep_area.py`: `run_sweep(..., extract=Callable[[], None])` com fase `extraindo`; `_real_extract(session)` usa FlyerSource+run_ingestion; `_events_for_shortcodes` filtra `source_type == "vision_flyer"`; report por item tem `festas`/`flyers`; `_norm` local (lower+NFD).
- `ingestion/pipeline.py`: `venue_by_handle(session, handle)` público (D-1); `run_ingestion` continua servindo RA/Sympla/Places — NÃO mexa no fluxo deles.
- `persistence/inputs.py::EventInput {name, starts_at, ends_at, venue_id, venue_name, organizer, organizer_id, lineup_text, genre, ticket_url, raw_fields}`; `SourceInfo {source_type, source_url, raw_payload}`; `events_repo.upsert_event(session, candidate, source, *, reference)`.
- `models.py`: `Event.status` (string, "scheduled"/...), `VerificationLog {entity_type, entity_id, note, created_at}` (ver uso: `grep -rn "VerificationLog(" src/`).
- `api/main.py::list_events`: default `date_from = date.today()` quando sem include_past; filtros `Event.starts_at >= _sp_day_start(...)` / `< _sp_day_start(date_to+1)`; `_flyer_urls_for` NÃO filtra por source_type (flyer_url continua funcionando).
- `domain/dates_ptbr.py::parse_ptbr_datetime(text, *, reference, tz="America/Sao_Paulo") -> ParsedDate` (`.dt` tz-aware ou None).
- `ingestion/places_source.py`: `SEED_POINTS` (20), `SEARCH_TYPES`, `_SEARCH_RADIUS_M=1000`, `_MIN_SUBDIVIDE_RADIUS_M=150`, `_MAX_SUBDIVIDE_DEPTH=3`, `PlacesSource(client, *, seeds, types, radius, log)`; `ingestion/places_client.py::PlacesClient` (httpx único; `search_nearby`, `place_details` — ver field masks lá).
- `discover_places.py::main`: sem argparse hoje; `truststore.inject_into_ssl()` obrigatório (Avast); exige `GOOGLE_MAPS_API_KEY`.
- Web: `EventCard.fmtDate(null)` já devolve `'data a confirmar'`; `data/hero.ts::pickHero` (1º com flyer); `MapaTab` passa `events` direto pro MapView e pro Drawer; `SweepReport` tabela por item; `api/sweep.ts::SweepItem`.
- Testes: backend `.venv/Scripts/python -m pytest <arq> -v` (Postgres `docker compose up -d --wait`; suíte cheia/tmp_path com `--basetemp=.pytest-tmp`, deletar depois; fixture `session` no conftest); web `cd web && npx vitest run <arq>` + `npx tsc -b`.

**Convenção de commit:** trailer `Claude-Session: b9eb4ce7-361b-434d-9809-31614b56e56d`. **Branch:** `feat/e1-interprete-posts`.

---

### Task 1: Plomberia compartilhada do codex (`ingestion/codex_cli.py`)

**Files:**
- Create: `src/nightlife/ingestion/codex_cli.py`
- Modify: `src/nightlife/ingestion/codex_extractor.py` (passa a importar)
- Test: nenhum novo (os testes existentes do extractor continuam verdes — é MOVE, não rewrite)

- [ ] **Step 1:** MOVA `_run_codex` e `_extract_json` de `codex_extractor.py` para o novo `src/nightlife/ingestion/codex_cli.py` com nomes públicos `run_codex` e `extract_json` — docstrings INTACTOS (as lições de Windows/segurança). `codex_extractor.py` importa de lá (`from .codex_cli import extract_json, run_codex`) e mantém aliases internos se os testes usarem os nomes privados (confira com `grep -rn "_run_codex\|_extract_json" tests/`).
- [ ] **Step 2:** Run: `.venv/Scripts/python -m pytest tests/ -k "codex or extractor" -v` → PASS (ajuste o -k ao nome real dos arquivos).
- [ ] **Step 3:** Commit: `refactor: plomberia do codex CLI vira modulo compartilhado (run_codex/extract_json)`

---

### Task 2: Contrato `PostInterpretation` + saneamento (`extraction/post_actions.py`)

**Files:**
- Create: `src/nightlife/extraction/post_actions.py`
- Test: `tests/test_post_actions.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_post_actions.py
from nightlife.extraction.post_actions import (
    AddEvent, CancelEvent, Ignore, PostInterpretation, UpdateEvent, sanitize_actions,
)


def _add(name="Festa X", quotes=None, confidence=None, **kw):
    return AddEvent(name=name, quotes=quotes or {}, confidence=confidence or {}, **kw)


def test_parse_uniao_discriminada():
    interp = PostInterpretation.model_validate({"actions": [
        {"type": "add_event", "name": "NOITE 1", "date_text": "SEX 18/07",
         "quotes": {"name": "NOITE 1", "date_text": "SEX 18/07"},
         "confidence": {"name": 0.9, "date_text": 0.9}},
        {"type": "cancel_event", "event_name": "WE LOVE POP", "quote": "CANCELADA", "confidence": 0.9},
        {"type": "ignore", "reason": "aniversario"},
    ]})
    assert [a.type for a in interp.actions] == ["add_event", "cancel_event", "ignore"]


def test_sanitize_add_sem_quote_do_nome_cai():
    interp = PostInterpretation(actions=[
        _add(quotes={}, confidence={"name": 0.9}),                       # sem quote: 0.45 < 0.5 -> cai
        _add(name="OK", quotes={"name": "OK"}, confidence={"name": 0.9}),
    ])
    out = sanitize_actions(interp)
    assert [a.name for a in out.actions] == ["OK"]


def test_sanitize_data_sem_quote_vira_none_mas_evento_fica():
    interp = PostInterpretation(actions=[
        _add(name="OK", date_text="18/07", quotes={"name": "OK"},
             confidence={"name": 0.9, "date_text": 0.9}),
    ])
    out = sanitize_actions(interp)
    assert out.actions[0].date_text is None      # data alucinada e pior que sem data
    assert out.actions[0].name == "OK"


def test_sanitize_cancel_update_exigem_quote_e_confianca():
    interp = PostInterpretation(actions=[
        CancelEvent(event_name="A", quote=None, confidence=0.9),          # sem quote -> cai
        CancelEvent(event_name="B", quote="CANCELADA", confidence=0.3),   # conf baixa -> cai
        CancelEvent(event_name="C", quote="ADIADA", confidence=0.8),      # fica
        UpdateEvent(event_name="D", changes={"date_text": "25/07"}, quote=None, confidence=0.9),
    ])
    out = sanitize_actions(interp)
    assert [a.event_name for a in out.actions] == ["C"]


def test_ignore_sempre_passa():
    interp = PostInterpretation(actions=[Ignore(reason="esporte", note="jogo do brasil")])
    assert len(sanitize_actions(interp).actions) == 1
```

- [ ] **Step 2:** Run: `.venv/Scripts/python -m pytest tests/test_post_actions.py -v` → FAIL (módulo não existe)

- [ ] **Step 3: Implement**

```python
# src/nightlife/extraction/post_actions.py
"""Contrato do interprete de posts (spec E-1 §3.1): o modelo devolve ACOES,
nao campos. Anti-alucinacao POR ACAO: quote sustenta, senao a acao (ou o
campo) cai — mesmo espirito do adjusted_confidence do contrato antigo."""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

IgnoreReason = Literal["aula", "aniversario", "institucional", "esporte",
                       "repost", "sem_evento", "outro"]


class AddEvent(BaseModel):
    type: Literal["add_event"] = "add_event"
    name: str
    date_text: str | None = None       # CRU PT-BR; quem converte e o dates_ptbr
    time_text: str | None = None
    lineup: list[str] = Field(default_factory=list)
    genre: str | None = None
    ticket_url: str | None = None
    quotes: dict[str, str] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)


class CancelEvent(BaseModel):
    type: Literal["cancel_event"] = "cancel_event"
    event_name: str
    event_date_text: str | None = None
    quote: str | None = None           # prova textual obrigatoria pra efetivar
    confidence: float = 0.0


class UpdateEvent(BaseModel):
    type: Literal["update_event"] = "update_event"
    event_name: str
    event_date_text: str | None = None
    changes: dict[str, str] = Field(default_factory=dict)   # date_text | name | ticket_url
    quote: str | None = None
    confidence: float = 0.0


class Ignore(BaseModel):
    type: Literal["ignore"] = "ignore"
    reason: IgnoreReason = "outro"
    note: str | None = None


Action = Annotated[Union[AddEvent, CancelEvent, UpdateEvent, Ignore],
                   Field(discriminator="type")]


class PostInterpretation(BaseModel):
    actions: list[Action] = Field(default_factory=list)


def _adjusted(a: AddEvent, field: str) -> float:
    c = a.confidence.get(field, 0.0)
    return c if field in a.quotes else c / 2


def sanitize_actions(interp: PostInterpretation) -> PostInterpretation:
    """Gate por acao: add sem quote de nome cai inteiro; campos secundarios
    suspeitos (data/ticket) viram None mas o evento fica (data alucinada e
    pior que DATA A CONFIRMAR); cancel/update sem quote OU confianca < 0.5
    caem (nunca efetivar mudanca destrutiva por palpite)."""
    out: list[Action] = []
    for a in interp.actions:
        if isinstance(a, AddEvent):
            if _adjusted(a, "name") < 0.5:
                continue
            if a.date_text and _adjusted(a, "date_text") < 0.5:
                a = a.model_copy(update={"date_text": None})
            if a.ticket_url and _adjusted(a, "ticket_url") < 0.5:
                a = a.model_copy(update={"ticket_url": None})
            out.append(a)
        elif isinstance(a, (CancelEvent, UpdateEvent)):
            if a.quote and a.confidence >= 0.5:
                out.append(a)
        else:
            out.append(a)
    return PostInterpretation(actions=out)
```

- [ ] **Step 4:** Run → PASS. **Step 5:** Commit: `feat(extraction): contrato PostInterpretation — acoes add/cancel/update/ignore com saneamento por quote`

---

### Task 3: Intérprete (`ingestion/post_interpreter.py`)

**Files:**
- Create: `src/nightlife/ingestion/post_interpreter.py`
- Test: `tests/test_post_interpreter.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_post_interpreter.py
import json
from pathlib import Path

from nightlife.ingestion.post_interpreter import (
    Document, PostInterpreter, VenueContext, build_prompt,
)


CTX = VenueContext(venue_name="Selva Club", handle="selva.011", today_iso="2026-07-11",
                   known_events=[("WE LOVE POP", "2026-07-18"), ("NOITE X", None)])
DOC = Document(kind="ig_post", image_path=Path("x.jpg"), caption="mes de julho lotado",
               handle="selva.011", permalink="https://www.instagram.com/p/ABC/")


def test_build_prompt_injeta_contexto_e_legenda():
    p = build_prompt(DOC, CTX)
    for esperado in ("Selva Club", "@selva.011", "2026-07-11",
                     "WE LOVE POP (2026-07-18)", "NOITE X (data desconhecida)",
                     "mes de julho lotado", "add_event", "cancel_event", "ignore"):
        assert esperado in p


def test_interpret_parseia_acoes_do_runner():
    payload = {"actions": [
        {"type": "add_event", "name": "A", "date_text": "SEX 18/07",
         "quotes": {"name": "A", "date_text": "SEX 18/07"},
         "confidence": {"name": 0.9, "date_text": 0.9}},
        {"type": "add_event", "name": "B",
         "quotes": {"name": "B"}, "confidence": {"name": 0.8}},
    ]}
    fake = lambda image, prompt: f"blabla {json.dumps(payload)} tchau"
    it = PostInterpreter(runner=fake)
    out = it.interpret(DOC, CTX)
    assert [a.name for a in out.actions] == ["A", "B"]


def test_interpret_retry_e_none_em_lixo_persistente():
    calls = []
    def fake(image, prompt):
        calls.append(prompt)
        return "isso nao e json"
    it = PostInterpreter(runner=fake, retries=1)
    assert it.interpret(DOC, CTX) is None
    assert len(calls) == 2
    assert "invalida" in calls[1]     # re-prompt de correcao, padrao do CodexExtractor
```

- [ ] **Step 2:** Run → FAIL (módulo não existe)

- [ ] **Step 3: Implement**

```python
# src/nightlife/ingestion/post_interpreter.py
"""Interprete de posts (spec E-1 §3.2): imagem + legenda INTEIRA + contexto do
venue -> PostInterpretation (acoes). Runner injetavel: testes offline nao
gastam cota. web_page pluga no E-2 pelo mesmo contrato."""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from pydantic import ValidationError

from ..extraction.post_actions import PostInterpretation
from .codex_cli import extract_json, run_codex

_log = logging.getLogger(__name__)


@dataclass
class Document:
    kind: Literal["ig_post"]           # "web_page" entra no E-2
    image_path: Path
    caption: str | None
    handle: str | None
    permalink: str | None


@dataclass
class VenueContext:
    venue_name: str | None
    handle: str | None
    today_iso: str
    known_events: list[tuple[str, str | None]] = field(default_factory=list)  # (nome, data ISO|None)


_PROMPT_BASE = """Voce e o editor de uma agenda de vida noturna de Sao Paulo.
Vai receber a IMAGEM de um post de Instagram e a LEGENDA completa. Entenda o
post e decida ACOES sobre a agenda. Responda com UM UNICO objeto JSON, sem
markdown, exatamente neste formato:

{"actions": [
  {"type": "add_event", "name": str, "date_text": str|null, "time_text": str|null,
   "lineup": [str], "genre": str|null, "ticket_url": str|null,
   "quotes": {campo: trecho da imagem/legenda que sustenta},
   "confidence": {campo: 0.0 a 1.0}},
  {"type": "cancel_event", "event_name": str, "event_date_text": str|null,
   "quote": str, "confidence": 0.0 a 1.0},
  {"type": "update_event", "event_name": str, "event_date_text": str|null,
   "changes": {"date_text"?: str, "name"?: str, "ticket_url"?: str},
   "quote": str, "confidence": 0.0 a 1.0},
  {"type": "ignore", "reason": "aula|aniversario|institucional|esporte|repost|sem_evento|outro",
   "note": str|null}
]}

Regras:
- Post com UMA festa -> um add_event. Post-AGENDA (programacao da semana/mes)
  -> um add_event POR festa listada, cada um com sua data.
- date_text: copie o texto da data EXATAMENTE como esta (ex: "SEX 18/07 23h").
  Nao converta, nao calcule. Sem data legivel -> null.
- Post que NAO anuncia festa (aula, curso, aniversario de cliente, transmissao
  de jogo, institucional, sorteio, cardapio) -> ignore com o reason certo.
- Se o post anuncia festa que JA ESTA na lista de eventos conhecidos abaixo
  (mesmo nome, mesma data) -> ignore com reason "repost".
- Se anuncia CANCELAMENTO ou ADIAMENTO de evento conhecido -> cancel_event ou
  update_event com quote da prova ("CANCELADA", "adiada para...").
- quotes/quote: SEMPRE o trecho literal que sustenta. NUNCA invente."""


def build_prompt(doc: Document, ctx: VenueContext) -> str:
    known = "\n".join(
        f"- {n} ({d or 'data desconhecida'})" for n, d in ctx.known_events
    ) or "- (nenhum)"
    partes = [
        _PROMPT_BASE,
        f"\nCONTEXTO:\n- Local: {ctx.venue_name or '?'} (@{ctx.handle or '?'})",
        f"- Hoje: {ctx.today_iso}",
        f"- Eventos futuros JA CONHECIDOS deste local:\n{known}",
        f"\nLEGENDA DO POST:\n{doc.caption or '(sem legenda)'}",
    ]
    return "\n".join(partes)


class PostInterpreter:
    def __init__(self, *, runner: Callable[[Path, str], str] | None = None,
                 retries: int = 1) -> None:
        self._runner = runner or run_codex
        self._retries = retries

    def interpret(self, doc: Document, ctx: VenueContext) -> PostInterpretation | None:
        base = build_prompt(doc, ctx)
        prompt = base
        for attempt in range(self._retries + 1):
            try:
                output = self._runner(doc.image_path, prompt)
                return PostInterpretation.model_validate(extract_json(output))
            except (ValueError, json.JSONDecodeError, ValidationError,
                    subprocess.SubprocessError, OSError) as exc:
                _log.warning("interpretacao de %s falhou (tentativa %d): %s",
                             doc.image_path, attempt + 1, exc)
                prompt = (base + "\n\nATENCAO: sua resposta anterior foi invalida "
                          f"({exc}). Responda APENAS com o objeto JSON.")
        return None
```

- [ ] **Step 4:** Run → PASS. **Step 5:** Commit: `feat(ingestion): PostInterpreter — prompt com contexto do venue + runner injetavel`

---

### Task 4: Executor de ações (`persistence/action_executor.py`)

**Files:**
- Create: `src/nightlife/persistence/action_executor.py`
- Test: `tests/test_action_executor.py`

Comportamentos (spec §3.3): `add` → upsert com ancoragem por handle e `starts_at` NULL permitido, `source_type="vision_flyer"` (continuidade: `_events_for_shortcodes` do sweep e sinais de confiança já esperam esse tipo); `cancel` → match forte (nome normalizado + data igual, OU candidato único sem-data) → `status="cancelled"` + VerificationLog, senão `cancel_candidate` em VerificationLog e evento intacto; `update` → mesmo match, aplica changes + log; sem match → vira add; `ignore` → só conta.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_action_executor.py
from datetime import date, datetime, timezone

from nightlife.extraction.post_actions import (
    AddEvent, CancelEvent, Ignore, PostInterpretation, UpdateEvent,
)
from nightlife.ingestion.post_interpreter import Document
from nightlife.models import Event, VerificationLog, Venue
from nightlife.persistence.action_executor import execute_actions
from pathlib import Path

REF = date(2026, 7, 11)


def _doc(handle="selva.011"):
    return Document(kind="ig_post", image_path=Path("x.jpg"), caption=None,
                    handle=handle, permalink="https://www.instagram.com/p/ABC/")


def _venue(session, name="Selva Club", handle="selva.011"):
    v = Venue(name=name, instagram=handle, lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    return v


def _add(name, date_text=None):
    q = {"name": name}
    c = {"name": 0.9}
    if date_text:
        q["date_text"] = date_text
        c["date_text"] = 0.9
    return AddEvent(name=name, date_text=date_text, quotes=q, confidence=c)


def test_add_multi_evento_ancora_por_handle_e_permite_sem_data(session):
    v = _venue(session)
    interp = PostInterpretation(actions=[_add("NOITE 1", "SEX 18/07"), _add("TEASER")])
    stats = execute_actions(session, _doc(), interp, reference=REF)
    evs = session.query(Event).filter(Event.venue_id == v.id).all()
    assert {e.name for e in evs} == {"NOITE 1", "TEASER"}
    com_data = next(e for e in evs if e.name == "NOITE 1")
    sem_data = next(e for e in evs if e.name == "TEASER")
    assert com_data.starts_at is not None
    assert sem_data.starts_at is None            # DATA A CONFIRMAR
    assert stats["add"] == 2


def test_cancel_com_prova_forte_cancela_e_loga(session):
    v = _venue(session)
    ev = Event(name="WE LOVE POP", status="scheduled", confidence=50, venue_id=v.id,
               starts_at=datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc))  # SP: 18/07 22h
    session.add(ev)
    session.flush()
    interp = PostInterpretation(actions=[
        CancelEvent(event_name="we love pop", event_date_text="18/07",
                    quote="CANCELADA", confidence=0.9)])
    stats = execute_actions(session, _doc(), interp, reference=REF)
    assert ev.status == "cancelled"
    assert stats["cancel"] == 1
    assert session.query(VerificationLog).filter(
        VerificationLog.note.ilike("%cancelado%")).count() == 1


def test_cancel_sem_match_forte_vira_candidato_e_nao_toca(session):
    v = _venue(session)
    a = Event(name="FESTA", status="scheduled", confidence=50, venue_id=v.id,
              starts_at=datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc))
    b = Event(name="FESTA", status="scheduled", confidence=50, venue_id=v.id,
              starts_at=datetime(2026, 7, 25, 2, 0, tzinfo=timezone.utc))
    session.add_all([a, b])
    session.flush()
    interp = PostInterpretation(actions=[
        CancelEvent(event_name="FESTA", quote="cancelamos", confidence=0.8)])  # SEM data: 2 candidatos
    stats = execute_actions(session, _doc(), interp, reference=REF)
    assert a.status == "scheduled" and b.status == "scheduled"
    assert stats["cancel_candidate"] == 1
    assert session.query(VerificationLog).filter(
        VerificationLog.note.ilike("%cancel_candidate%")).count() == 1


def test_update_com_match_muda_data_e_sem_match_vira_add(session):
    v = _venue(session)
    ev = Event(name="NOITE X", status="scheduled", confidence=50, venue_id=v.id,
               starts_at=datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc))  # SP: 18/07 22h
    session.add(ev)
    session.flush()
    interp = PostInterpretation(actions=[
        UpdateEvent(event_name="NOITE X", event_date_text="18/07",
                    changes={"date_text": "SAB 25/07"}, quote="adiada para 25/07", confidence=0.9),
        UpdateEvent(event_name="INEDITA", changes={"date_text": "26/07"},
                    quote="nova data 26/07", confidence=0.9),
    ])
    stats = execute_actions(session, _doc(), interp, reference=REF)
    assert ev.starts_at.astimezone(__import__('zoneinfo').ZoneInfo('America/Sao_Paulo')).day == 25
    assert stats["update"] == 1
    assert session.query(Event).filter(Event.name == "INEDITA").count() == 1  # virou add
    assert stats["add"] == 1


def test_ignore_so_conta(session):
    _venue(session)
    interp = PostInterpretation(actions=[Ignore(reason="esporte")])
    stats = execute_actions(session, _doc(), interp, reference=REF)
    assert stats["ignore"] == {"esporte": 1}
    assert session.query(Event).count() == 0
```

- [ ] **Step 2:** Run → FAIL (módulo não existe). Confira antes os kwargs de `VerificationLog` no models.py.

- [ ] **Step 3: Implement**

```python
# src/nightlife/persistence/action_executor.py
"""Executa as acoes do interprete (spec E-1 §3.3). Cancel/update so com match
FORTE (nome normalizado + data; ou candidato unico) — mudanca destrutiva sem
certeza vira candidato auditavel em verification_logs."""
from __future__ import annotations

import unicodedata
from datetime import date
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.dates_ptbr import parse_ptbr_datetime
from ..extraction.post_actions import (
    AddEvent, CancelEvent, Ignore, PostInterpretation, UpdateEvent,
)
from ..ingestion.pipeline import venue_by_handle
from ..models import Event, VerificationLog
from .events_repo import upsert_event
from .inputs import EventInput, SourceInfo

if TYPE_CHECKING:
    from ..ingestion.post_interpreter import Document


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower().strip())
                   if unicodedata.category(c) != "Mn")


_SP_TZ = ZoneInfo("America/Sao_Paulo")


def _sp_day(dt) -> "date":
    # dia do CALENDARIO SP, nao UTC — festa sab 23h SP e domingo em UTC
    # (mesma licao do fix de datas do C-1)
    return dt.astimezone(_SP_TZ).date()


def _match_event(session: Session, venue_id: int | None, name: str,
                 date_text: str | None, *, reference: date) -> Event | None:
    """Match forte: mesmo venue + nome normalizado igual + (mesmo dia-SP OU
    candidato unico). Ambiguidade -> None (vira candidato, nunca chuta)."""
    if venue_id is None:
        return None
    candidates = [e for e in session.scalars(
        select(Event).where(Event.venue_id == venue_id, Event.status != "cancelled"))
        if _norm(e.name) == _norm(name)]
    if not candidates:
        return None
    if date_text:
        alvo = parse_ptbr_datetime(date_text, reference=reference).dt
        if alvo is not None:
            same_day = [e for e in candidates
                        if e.starts_at is not None and _sp_day(e.starts_at) == _sp_day(alvo)]
            if len(same_day) == 1:
                return same_day[0]
            return None
    return candidates[0] if len(candidates) == 1 else None


def _do_add(session: Session, doc: "Document", a: AddEvent, *, reference: date) -> None:
    starts = None
    if a.date_text:
        starts = parse_ptbr_datetime(a.date_text, reference=reference).dt
    venue = venue_by_handle(session, doc.handle)
    raw_fields: dict = {"raw": a.model_dump_json()}
    if venue is not None:
        raw_fields["anchored_by"] = "ig_handle"
    upsert_event(
        session,
        EventInput(name=a.name, starts_at=starts,
                   venue_id=venue.id if venue is not None else None,
                   genre=a.genre, ticket_url=a.ticket_url,
                   lineup_text=", ".join(a.lineup) or None,
                   raw_fields=raw_fields),
        SourceInfo(source_type="vision_flyer", source_url=doc.permalink,
                   raw_payload=a.model_dump_json()),
        reference=reference,
    )


def execute_actions(session: Session, doc: "Document",
                    interp: PostInterpretation, *, reference: date) -> dict:
    stats: dict = {"add": 0, "cancel": 0, "cancel_candidate": 0,
                   "update": 0, "ignore": {}}
    venue = venue_by_handle(session, doc.handle)
    vid = venue.id if venue is not None else None

    for a in interp.actions:
        if isinstance(a, AddEvent):
            _do_add(session, doc, a, reference=reference)
            stats["add"] += 1
        elif isinstance(a, CancelEvent):
            ev = _match_event(session, vid, a.event_name, a.event_date_text,
                              reference=reference)
            if ev is not None:
                ev.status = "cancelled"
                session.add(VerificationLog(
                    entity_type="event", entity_id=ev.id,
                    note=f"cancelado via ig_post {doc.permalink} (quote: {a.quote!r})"))
                stats["cancel"] += 1
            else:
                session.add(VerificationLog(
                    entity_type="venue", entity_id=vid or 0,
                    note=(f"cancel_candidate: {a.event_name!r} "
                          f"({a.event_date_text or 'sem data'}) via {doc.permalink} "
                          f"(quote: {a.quote!r}) — sem match forte")))
                stats["cancel_candidate"] += 1
        elif isinstance(a, UpdateEvent):
            ev = _match_event(session, vid, a.event_name, a.event_date_text,
                              reference=reference)
            if ev is not None:
                if "date_text" in a.changes:
                    novo = parse_ptbr_datetime(a.changes["date_text"], reference=reference).dt
                    if novo is not None:
                        ev.starts_at = novo
                if "name" in a.changes:
                    ev.name = a.changes["name"]
                if "ticket_url" in a.changes:
                    ev.ticket_url = a.changes["ticket_url"]
                session.add(VerificationLog(
                    entity_type="event", entity_id=ev.id,
                    note=f"atualizado via ig_post {doc.permalink} (quote: {a.quote!r})"))
                stats["update"] += 1
            else:
                # "adiada para X" de festa que nao temos = festa nova com data X
                add = AddEvent(name=a.changes.get("name", a.event_name),
                               date_text=a.changes.get("date_text", a.event_date_text),
                               ticket_url=a.changes.get("ticket_url"),
                               quotes={"name": a.quote or a.event_name},
                               confidence={"name": a.confidence})
                _do_add(session, doc, add, reference=reference)
                stats["add"] += 1
        elif isinstance(a, Ignore):
            stats["ignore"][a.reason] = stats["ignore"].get(a.reason, 0) + 1
    return stats
```

Ajuste os kwargs de `VerificationLog` ao modelo real (confira `entity_type/entity_id/note`). Se `entity_id` não aceitar 0, use o id do venue ou torne nullable a escolha — siga o padrão dos usos existentes.

- [ ] **Step 4:** Run: `.venv/Scripts/python -m pytest tests/test_action_executor.py -v` → PASS
- [ ] **Step 5:** Commit: `feat(persistence): executor de acoes — add multi/cancel forte/update-ou-add/ignore contado`

---

### Task 5: Fluxo `post_flow.process_inbox` + rewire `ingest_flyers`/`sweep_area`

**Files:**
- Create: `src/nightlife/ingestion/post_flow.py`
- Modify: `src/nightlife/ingest_flyers.py`, `src/nightlife/sweep_area.py`
- Test: `tests/test_post_flow.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_post_flow.py
import json
from datetime import date

from nightlife.extraction.post_actions import AddEvent, Ignore, PostInterpretation
from nightlife.ingestion.post_flow import process_inbox
from nightlife.models import Event, IngestionRun, Venue

REF = date(2026, 7, 11)


class FakeInterpreter:
    def __init__(self, by_stem):
        self.by_stem = by_stem
        self.calls = []
    def interpret(self, doc, ctx):
        self.calls.append((doc, ctx))
        return self.by_stem.get(doc.image_path.stem)


def _post(tmp_path, stem, handle="selva.011", caption="legenda"):
    (tmp_path / f"{stem}.jpg").write_bytes(stem.encode() * 50)   # dHash distinto por stem
    (tmp_path / f"{stem}.json").write_text(json.dumps(
        {"handle": handle, "caption": caption,
         "permalink": f"https://www.instagram.com/p/{stem}/"}), encoding="utf-8")


def test_process_inbox_interpreta_executa_e_separa_paths(session, tmp_path):
    v = Venue(name="Selva Club", instagram="selva.011", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    _post(tmp_path, "OK1")
    _post(tmp_path, "IGN1")
    _post(tmp_path, "FAIL1")
    fake = FakeInterpreter({
        "OK1": PostInterpretation(actions=[AddEvent(
            name="NOITE 1", date_text="SEX 18/07",
            quotes={"name": "NOITE 1", "date_text": "SEX 18/07"},
            confidence={"name": 0.9, "date_text": 0.9})]),
        "IGN1": PostInterpretation(actions=[Ignore(reason="esporte")]),
        # FAIL1 ausente -> interpret devolve None -> failed
    })
    flow = process_inbox(session, tmp_path, fake, reference=REF)
    assert session.query(Event).filter_by(name="NOITE 1").one().venue_id == v.id
    stems_ok = {p.stem for p in flow.processed_paths}
    stems_fail = {p.stem for p in flow.failed_paths}
    assert stems_ok == {"OK1", "IGN1"}
    assert stems_fail == {"FAIL1"}
    assert flow.stats_by_handle["selva.011"]["add"] == 1
    assert flow.stats_by_handle["selva.011"]["ignore"] == {"esporte": 1}
    run = session.query(IngestionRun).order_by(IngestionRun.id.desc()).first()
    assert run.source == "posts"
    assert run.records_created == 1
    # contexto passado ao interprete inclui o venue dono do handle
    assert fake.calls[0][1].venue_name == "Selva Club"


def test_process_inbox_dhash_dedupe_nao_reinterpreta(session, tmp_path):
    _post(tmp_path, "AAA")
    (tmp_path / "BBB.jpg").write_bytes(b"AAA" * 50)   # MESMO conteudo -> mesmo dHash
    (tmp_path / "BBB.json").write_text("{}", encoding="utf-8")
    fake = FakeInterpreter({"AAA": PostInterpretation(actions=[Ignore(reason="sem_evento")])})
    flow = process_inbox(session, tmp_path, fake, reference=REF)
    assert len(fake.calls) == 1                        # BBB nem chamou o interprete
    assert {p.stem for p in flow.processed_paths} == {"AAA", "BBB"}
```

- [ ] **Step 2:** Run → FAIL. (Se o dHash dos dois arquivos sintéticos NÃO coincidir por detalhe do algoritmo, gere BBB copiando o arquivo AAA byte a byte.)

- [ ] **Step 3: Implement**

```python
# src/nightlife/ingestion/post_flow.py
"""Orquestra o inbox de posts (spec E-1 §3.4): dHash dedupe -> Document ->
interprete -> saneamento -> executor. processed/failed sao movidos pelo
CALLER (padrao do FlyerSource). IngestionRun label='posts'."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..extraction.imagehash import dhash
from ..extraction.post_actions import sanitize_actions
from ..models import Event, IngestionRun, Venue
from .post_interpreter import Document, PostInterpreter, VenueContext

_log = logging.getLogger(__name__)
_IMAGE_GLOBS = ("*.jpg", "*.jpeg", "*.png", "*.webp")
_SP_TZ = ZoneInfo("America/Sao_Paulo")
_KNOWN_CAP = 20


@dataclass
class FlowStats:
    processed_paths: list[Path] = field(default_factory=list)
    failed_paths: list[Path] = field(default_factory=list)
    stats_by_handle: dict[str, dict] = field(default_factory=dict)
    created: int = 0


def _context_for(session: Session, handle: str | None, today: date) -> VenueContext:
    venue = None
    if handle:
        venue = session.scalars(
            select(Venue).where(Venue.instagram == handle)
            .order_by(Venue.confidence.desc(), Venue.id)).first()
    known: list[tuple[str, str | None]] = []
    if venue is not None:
        now = datetime.now(timezone.utc)
        for e in session.scalars(
                select(Event).where(Event.venue_id == venue.id,
                                    Event.status != "cancelled")
                .order_by(Event.starts_at.asc().nullslast()).limit(_KNOWN_CAP)):
            if e.starts_at is None or e.starts_at >= now:
                known.append((e.name, e.starts_at.date().isoformat() if e.starts_at else None))
    return VenueContext(venue_name=venue.name if venue else None, handle=handle,
                        today_iso=today.isoformat(), known_events=known)


def _merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if k == "ignore":
            ig = dst.setdefault("ignore", {})
            for r, n in v.items():
                ig[r] = ig.get(r, 0) + n
        else:
            dst[k] = dst.get(k, 0) + v


def process_inbox(session: Session, inbox: Path, interpreter: PostInterpreter,
                  *, reference: date, log=print) -> FlowStats:
    from ..persistence.action_executor import execute_actions

    run = IngestionRun(source="posts", status="running")
    session.add(run)
    session.flush()
    flow = FlowStats()
    seen_hashes: set[str] = set()
    found = 0

    images = sorted(p for g in _IMAGE_GLOBS for p in inbox.glob(g))
    for path in images:
        image_hash = dhash(path)
        if image_hash in seen_hashes:
            flow.processed_paths.append(path)     # duplicata: nao gasta interpretacao
            continue
        seen_hashes.add(image_hash)
        found += 1

        caption = handle = permalink = None
        sidecar = path.with_suffix(".json")
        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
                caption, handle, permalink = (meta.get("caption"), meta.get("handle"),
                                              meta.get("permalink"))
            except (ValueError, OSError):
                pass

        doc = Document(kind="ig_post", image_path=path, caption=caption,
                       handle=handle, permalink=permalink or f"flyer:{image_hash}")
        interp = interpreter.interpret(doc, _context_for(session, handle, reference))
        if interp is None:
            _log.warning("post %s: interpretacao falhou (codex) — failed/", path.name)
            flow.failed_paths.append(path)
            continue
        stats = execute_actions(session, doc, sanitize_actions(interp),
                                reference=reference)
        flow.created += stats["add"]
        if handle:
            _merge(flow.stats_by_handle.setdefault(handle, {}), stats)
        flow.processed_paths.append(path)
        session.commit()                          # progresso por post (runs longos)

    run.status = "finished"
    run.records_found = found
    run.records_created = flow.created
    run.finished_at = datetime.now(timezone.utc)
    session.commit()
    return flow
```

Rewire `ingest_flyers.py::main`: troque `FlyerSource+run_ingestion` por

```python
    from .ingestion.post_flow import process_inbox
    from .ingestion.post_interpreter import PostInterpreter
    ...
    flow = process_inbox(session, FLYERS_DIR, PostInterpreter(), reference=date.today())
    session.commit()
    print(f"posts: {len(flow.processed_paths)} processados, "
          f"{len(flow.failed_paths)} falhas | eventos criados: {flow.created}")
    move_all(flow.processed_paths, FLYERS_DIR / "processed")
    move_all(flow.failed_paths, FLYERS_DIR / "failed")
```

Rewire `sweep_area.py::_real_extract`: idem (process_inbox + move_all), guardando `flow.stats_by_handle`; `run_sweep` passa a receber de `extract` o `stats_by_handle` (mude a assinatura do callable para `Callable[[], dict]` — os fakes dos testes existentes devolvem `{}`) e grava `item["acoes"] = stats_by_handle.get(item["handle"], {})` no loop pós-extração. Ajuste `tests/test_sweep_area.py` (fake_extract devolve dict; assert de `acoes` no item do aura).

- [ ] **Step 4:** Run: `.venv/Scripts/python -m pytest tests/test_post_flow.py tests/test_sweep_area.py -v --basetemp=.pytest-tmp` → PASS (delete `.pytest-tmp`)
- [ ] **Step 5:** Commit: `feat(ingestion): post_flow — inbox vira Documents interpretados; ingest_flyers e sweep_area no fluxo novo`

---

### Task 6: Aposentar o caminho antigo (FlyerSource/FlyerExtraction/CodexExtractor)

**Files:**
- Delete: `src/nightlife/ingestion/flyer_source.py`, `src/nightlife/ingestion/codex_extractor.py`, e o corpo de extração de `src/nightlife/extraction/flyer.py`
- Modify: quem importar (grep!)
- Test: DELETAR `tests/test_flyer_source.py` etc. SÓ se a cobertura equivalente existir nos novos (regra do projeto: substituir, não remover)

- [ ] **Step 1:** `grep -rn "FlyerSource\|CodexExtractor\|flyer_to_raw_event\|FlyerExtraction" src/ tests/` — mapeie todos os usos restantes. Esperado: só os módulos antigos entre si + seus testes (ingest_flyers/sweep_area já migraram na Task 5). `RawEvent.source_handle` e `venue_by_handle` FICAM (pipeline ainda serve RA/Sympla/Places).
- [ ] **Step 2:** Antes de deletar cada teste antigo, confirme a cobertura equivalente: anti-alucinação (test_post_actions), retry/JSON lixo (test_post_interpreter), dedupe dHash/sidecar (test_post_flow), datas cruas (dates_ptbr já tem suíte própria). O que não tiver equivalente → PORTE o teste pro módulo novo antes.
- [ ] **Step 3:** Delete os módulos + testes antigos; rode a suíte inteira: `.venv/Scripts/python -m pytest -q --basetemp=.pytest-tmp` → verde (delete `.pytest-tmp`).
- [ ] **Step 4:** Commit: `refactor: caminho antigo de flyer (FlyerSource/FlyerExtraction/CodexExtractor) sai — interprete assume`

---

### Task 7: API — sem-data visível, cancelado invisível

**Files:**
- Modify: `src/nightlife/api/main.py::list_events`
- Test: `tests/test_api_undated.py`

Regra: `status='cancelled'` NUNCA sai no list; `starts_at IS NULL` entra SÓ no modo default/upcoming (sem `date_to` explícito — quem pergunta "HOJE" quer um dia específico); ordenação com data primeiro, sem-data no fim.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_undated.py
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient

from nightlife.api.deps import get_session
from nightlife.api.main import app
from nightlife.models import Event, Venue


def _client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def _seed(session):
    v = Venue(name="Selva Club", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    fut = datetime.now(timezone.utc) + timedelta(days=7)
    session.add_all([
        Event(name="COM DATA", status="scheduled", confidence=50, venue_id=v.id, starts_at=fut),
        Event(name="SEM DATA", status="scheduled", confidence=50, venue_id=v.id, starts_at=None),
        Event(name="CANCELADA", status="cancelled", confidence=50, venue_id=v.id, starts_at=fut),
    ])
    session.flush()


def test_default_inclui_sem_data_no_fim_e_esconde_cancelada(session):
    _seed(session)
    client = _client(session)
    try:
        nomes = [e["name"] for e in client.get("/events").json()]
        assert "CANCELADA" not in nomes
        assert nomes.index("COM DATA") < nomes.index("SEM DATA")   # sem-data no fim
    finally:
        app.dependency_overrides.clear()


def test_janela_de_dia_especifico_exclui_sem_data(session):
    _seed(session)
    client = _client(session)
    try:
        hoje = datetime.now(timezone.utc).date().isoformat()
        nomes = [e["name"] for e in
                 client.get(f"/events?date_from={hoje}&date_to={hoje}").json()]
        assert "SEM DATA" not in nomes
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2:** Run → FAIL (SEM DATA hoje não aparece nunca; CANCELADA aparece)

- [ ] **Step 3: Implement** em `list_events` (import `or_` e `nullslast` de sqlalchemy):

```python
    q = select(Event).where(Event.confidence >= min_confidence,
                            Event.status != "cancelled")
    # sem-data (DATA A CONFIRMAR) so entra no modo "proximas" — quem pergunta
    # por um DIA especifico (date_to) quer aquele dia
    include_undated = date_to is None
    if date_from is not None:
        lower = Event.starts_at >= _sp_day_start(date_from)
        q = q.where(or_(lower, Event.starts_at.is_(None)) if include_undated else lower)
    if date_to is not None:
        q = q.where(Event.starts_at < _sp_day_start(date_to + timedelta(days=1)))
    ...
    session.scalars(q.order_by(nullslast(Event.starts_at.asc()))).all()
```

(`get_event` fica; `include_past=True` sem datas já inclui NULL por não ter filtro — confira que o teste de regressão do dia-SP existente segue verde.)

- [ ] **Step 4:** Run: `.venv/Scripts/python -m pytest tests/test_api_undated.py tests/test_api.py -v` → PASS
- [ ] **Step 5:** Commit: `feat(api): sem-data visivel no default (fim da lista) + cancelled fora`

---

### Task 8: UI — DATA A CONFIRMAR + mapa sem pin de sem-data + RELATÓRIO com ações

**Files:**
- Modify: `web/src/components/EventCard.tsx` (tag), `web/src/data/hero.ts` (hero prefere com-data), `web/src/tabs/MapaTab.tsx` (markers só com data), `web/src/components/SweepReport.tsx` + `web/src/api/sweep.ts` (coluna AÇÕES)
- Test: ajustes em `EventCard.test.tsx`, `hero.test.ts`, `MapaTab.test.tsx`, `SweepReport.test.tsx`

- [ ] **Step 1: Failing tests** (acrescente aos arquivos existentes, seguindo as fixtures deles):

```tsx
// EventCard.test.tsx
it('sem starts_at mostra a tag DATA A CONFIRMAR', () => {
  render(<EventCard event={{ ...base, starts_at: null }} variant="row" onOpen={() => {}} />)
  expect(screen.getByText('DATA A CONFIRMAR')).toBeInTheDocument()
})
// hero.test.ts
it('hero prefere evento COM data; sem-data so vira hero se nao houver outro com flyer', () => {
  const semData = evt({ id: 1, flyer_url: '/f/a.jpg', starts_at: null })
  const comData = evt({ id: 2, flyer_url: '/f/b.jpg', starts_at: '2026-07-18T02:00:00Z' })
  expect(pickHero([semData, comData]).hero?.id).toBe(2)
  expect(pickHero([semData]).hero?.id).toBe(1)
})
// MapaTab.test.tsx
it('evento sem data nao vira marker no mapa (mas segue na gaveta)', () => {
  const dated = evt(1, 10, new Date(2026, 6, 10, 23, 0).toISOString())
  const undated = { ...evt(2, 10, new Date().toISOString()), starts_at: null } as EventWithGeo
  render(<MapaTab {...base} events={[dated, undated]} />)
  const last = mapProps.mock.calls.at(-1)![0] as { events: { id: number }[] }
  expect(last.events.map((e) => e.id)).toEqual([1])
  expect(screen.getByText(/2 FESTAS NA ÁREA/)).toBeInTheDocument()  // gaveta conta as 2
})
// SweepReport.test.tsx
it('linha mostra o resumo de acoes quando presente', () => {
  const withAcoes = { ...sweep, report: [{ ...sweep.report[0],
    acoes: { add: 3, cancel: 1, ignore: { esporte: 2 } } }] }
  render(<SweepReport sweep={withAcoes} onClose={() => {}} />)
  expect(screen.getByText(/\+3 · ✕1 · ign 2/)).toBeInTheDocument()
})
```

- [ ] **Step 2:** Run → FAIL. **Step 3: Implement:**
- `EventCard`: nas duas variantes, quando `!event.starts_at`, renderize `<span className="tag ghost">DATA A CONFIRMAR</span>` junto das tags (hero) / após o meta (row). O `fmtDate` já diz 'data a confirmar' no texto — a tag dá o destaque.
- `hero.ts::pickHero`: entre os com `flyer_url`, prefira os com `starts_at != null`; fallback mantém o atual.
- `MapaTab`: `const mapEvents = useMemo(() => events.filter((e) => e.starts_at != null), [events])` e use `mapEvents` SÓ no `<MapView events={...}>` (gaveta/label continuam com `events`).
- `api/sweep.ts::SweepItem` ganha `acoes?: { add?: number; cancel?: number; update?: number; cancel_candidate?: number; ignore?: Record<string, number> }`.
- `SweepReport`: coluna AÇÕES: `+{add} · ✕{cancel} · ign {total ignore}` (célula `—` sem acoes; monte a string num helper puro exportado `acoesLabel(acoes)` pra testar direto se preferir).

- [ ] **Step 4:** `cd web && npx vitest run && npx tsc -b` → verde/limpo.
- [ ] **Step 5:** Commit: `feat(web): DATA A CONFIRMAR visivel, mapa so pinta com-data, RELATORIO com acoes`

---

### Task 9: Catálogo — `add_place` (Text Search) + `discover_places` denso

**Files:**
- Modify: `src/nightlife/ingestion/places_client.py` (novo método `search_text`), `src/nightlife/ingestion/places_source.py` (params `max_depth`/`min_radius`), `src/nightlife/discover_places.py` (argparse `--seed/--radius/--max-depth`)
- Create: `src/nightlife/add_place.py`
- Test: `tests/test_add_place.py`, acrescentar a `tests/test_places_source.py` (nome real via ls)

- [ ] **Step 1: Failing tests**

```python
# tests/test_add_place.py
from nightlife.add_place import ingest_pick, parse_matches


FAKE_RESPONSE = {"places": [
    {"id": "ChIJsupra123", "displayName": {"text": "Supra Club Augusta"},
     "formattedAddress": "R. Augusta, 765 - Consolação, São Paulo",
     "location": {"latitude": -23.5512, "longitude": -46.6531},
     "types": ["night_club", "bar"], "businessStatus": "OPERATIONAL"},
    {"id": "ChIJoutro456", "displayName": {"text": "Supra Bar"},
     "formattedAddress": "R. Alvaro Alvim, 76",
     "location": {"latitude": -23.556, "longitude": -46.641},
     "types": ["bar"], "businessStatus": "OPERATIONAL"},
]}


def test_parse_matches_extrai_campos_e_types():
    ms = parse_matches(FAKE_RESPONSE)
    assert ms[0].name == "Supra Club Augusta"
    assert ms[0].place_id == "ChIJsupra123"
    assert "night_club" in ms[0].types
    assert ms[0].lat == -23.5512


def test_ingest_pick_cria_venue_com_evidencia_places(session):
    from nightlife.models import Venue, VenueSource
    m = parse_matches(FAKE_RESPONSE)[0]
    v = ingest_pick(session, m, reference=__import__("datetime").date(2026, 7, 11))
    assert v.name == "Supra Club Augusta"
    assert v.lat == -23.5512
    assert v.category == "nightclub"          # night_club no types
    src = session.query(VenueSource).filter_by(venue_id=v.id).one()
    assert src.source_type == "google_places"
```

E no teste do places_source (acrescentar): `PlacesSource(client, seeds=[...], radius=400, max_depth=5, min_radius=100)` subdivide além do default (client fake devolvendo 20 resultados força a subdivisão; assert de que houve chamadas em profundidade > 3 — siga o padrão dos testes de subdivisão existentes no arquivo).

- [ ] **Step 2:** Run → FAIL. **Step 3: Implement:**
- `places_client.py::search_text(query, *, lat, lng, radius_m)`: POST `https://places.googleapis.com/v1/places:searchText`, body `{"textQuery": query, "languageCode": "pt-BR", "locationBias": {"circle": {"center": {...}, "radius": radius_m}}}`, field mask `places.id,places.displayName,places.formattedAddress,places.location,places.types,places.businessStatus` — siga o estilo/headers do `search_nearby` existente (mesmo httpx client).
- `places_source.py`: promova `_MAX_SUBDIVIDE_DEPTH`/`_MIN_SUBDIVIDE_RADIUS_M` a params do `__init__` (`max_depth=_MAX_SUBDIVIDE_DEPTH`, `min_radius=_MIN_SUBDIVIDE_RADIUS_M`) usados no `_search_cell`.
- `add_place.py`: `parse_matches(resp) -> list[Match]` (dataclass `Match {place_id, name, address, lat, lng, types, business_status}`), `ingest_pick(session, match, *, reference)` — monte `RawVenue` ESPELHANDO o formato do places_source (categoria via lógica `night_club∈types → "nightclub"` senão `"bar"`; `source_url` no MESMO formato que o places_source usa pro place_id — confira lá) e chame `upsert_venue` como o pipeline faz. `main()`: argparse `query` posicional + `--pick N`; exige GOOGLE_MAPS_API_KEY + truststore (copie o preâmbulo do discover_places); lista matches numerados com types e endereço; 1 match → ingere direto; N matches sem `--pick` → só lista e sai; loga os `types` (confirma a hipótese da saturação do Supra).
- `discover_places.py::main`: argparse `--seed <substring>` (match normalizado contra SEED_POINTS — reuse a normalização do sweep_area/resolve_bairro se importável, senão local), `--radius <m>` (default 1000), `--max-depth <n>` (default 3); com `--seed`, `PlacesSource(seeds=[semente], radius=args.radius, max_depth=args.max_depth, min_radius=100)`.

- [ ] **Step 4:** Run: `.venv/Scripts/python -m pytest tests/test_add_place.py tests/test_places_source.py -v` → PASS
- [ ] **Step 5:** Commit: `feat(places): add_place por Text Search + discover_places denso (--seed/--radius/--max-depth)`

---

### Task 10: Final — suítes + smokes reais do laboratório

- [ ] **Step 1:** Suítes completas: `.venv/Scripts/python -m pytest -q --basetemp=.pytest-tmp` (delete depois) + `cd web && npx vitest run && npx tsc -b && npm run build` → tudo verde.
- [ ] **Step 2 (smoke assistido, coordenador roda):** re-processar os failed/ da Selva pelo intérprete novo:
```bash
# devolve so os posts da selva pro inbox (imagem + sidecar)
.venv/Scripts/python - <<'EOF'
import json, shutil
from pathlib import Path
for sc in Path("flyers/failed").glob("*.json"):
    try:
        if json.loads(sc.read_text(encoding="utf-8")).get("handle") == "selva.011":
            for f in (sc, sc.with_suffix(".jpg")):
                if f.exists(): shutil.move(str(f), f"flyers/{f.name}")
    except ValueError: pass
EOF
.venv/Scripts/python -m nightlife.ingest_flyers
```
Expected: posts-agenda da Selva viram N `add_event` com datas; conferir via `/events` que as festas do mês da Selva existem (algumas talvez DATA A CONFIRMAR). **Este é o critério-âncora do E-1.**
- [ ] **Step 3 (smoke do usuário, precisa de GOOGLE_MAPS_API_KEY):** `add_place "supra club augusta"` (anotar types retornados) e `discover_places --seed "baixa augusta" --radius 400 --max-depth 5`; depois geocode/enrich se aplicável; conferir Supra no mapa.
- [ ] **Step 4 (smoke do usuário):** nova varredura por área pela UI; RELATÓRIO agora com coluna AÇÕES (ignores com motivo, cancels); conferir menos ruído (aula/jogo ignorados) e sem reposts duplicados.
- [ ] **Step 5:** Smoke aprovado → finishing-a-development-branch (merge no master).

---

## Riscos & notas pro executor

- **NUNCA chame o codex real em teste** — interpreter/flow recebem runner/interpreter fakes.
- **Não toque no fluxo RA/Sympla/Places do `run_ingestion`** — só o caminho IG migra.
- **`VerificationLog`**: confira os kwargs reais no models.py antes dos testes do executor.
- **`source_type` continua `"vision_flyer"`** nos adds (o `_events_for_shortcodes` do sweep e os sinais de confiança dependem disso) — mudar o nome do tipo é fora de escopo.
- **conftest**: fixture `session`; kwargs de modelos podem exigir ajuste (ajuste kwargs, não asserções).
- **Windows temp**: use `--basetemp=.pytest-tmp` em qualquer teste com tmp_path; delete depois.
- **Task 6 é DELETE disciplinado**: grep antes, porte cobertura órfã antes de apagar teste.
- **jsdom**: MapaTab.test mocka MapView e api/sweep (padrão existente).
