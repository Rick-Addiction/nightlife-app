# Nightlife App — Plano A: Núcleo de Domínio (lógica pura) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir e testar o núcleo de domínio puro do nightlife-app — normalização de datas PT-BR, confidence scoring, venue matching, deduplicação de eventos e extração (JSON-LD / HTML / texto livre com fallback determinístico) — sem nenhum banco, rede ou chave de API.

**Architecture:** Funções e dataclasses puras (sem I/O) em `src/nightlife/domain/` e `src/nightlife/extraction/`. Cada módulo tem uma responsabilidade única e é testável isoladamente com pytest. É a fundação reusada pelo Plano B (persistência + ingestão + API). Layout `src/`, instalado em modo editável.

**Tech Stack:** Python 3.14 · pytest · BeautifulSoup4 (parser `html.parser`, sem lxml) · stdlib (`difflib`, `re`, `unicodedata`, `zoneinfo`+`tzdata`, `dataclasses`, `json`). Sem extensões C — evita problemas de wheel no Python 3.14.

**Convenções:**
- Rode Python/pytest pelo interpretador do venv: `.venv/Scripts/python -m ...` (Windows). Não depende de `activate`.
- Todo commit termina com o trailer: `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`
- Cobre os 5 testes obrigatórios do spec (§13): datas PT-BR (Task 1), scoring (Task 2), venue matching (Task 3), dedupe (Task 4), JSON-LD (Task 5).

---

## File Structure

```
nightlife-app/
  pyproject.toml                      # metadados, deps, config do pytest (Task 0)
  .gitignore                          # (Task 0)
  src/nightlife/
    __init__.py
    domain/
      __init__.py
      dates_ptbr.py                   # parse_ptbr_datetime  (Task 1)
      scoring.py                      # score_venue / score_event  (Task 2)
      matching.py                     # normalize_name / name_similarity / match_venue  (Task 3)
      dedupe.py                       # dedupe_score / classify / compare  (Task 4)
    extraction/
      __init__.py
      base.py                         # ExtractedEvent (dataclass compartilhada)  (Task 5)
      jsonld.py                       # parse_jsonld_events  (Task 5)
      html_patterns.py                # parse_html_patterns  (Task 6)
      freetext.py                     # extract_freetext_deterministic  (Task 6)
  tests/
    test_dates_ptbr.py                # (Task 1)
    test_scoring.py                   # (Task 2)
    test_matching.py                  # (Task 3)
    test_dedupe.py                    # (Task 4)
    test_jsonld.py                    # (Task 5)
    test_extraction_text.py           # (Task 6)
```

Responsabilidades:
- `domain/` = regras de negócio puras (datas, score, similaridade, dedupe).
- `extraction/` = transformar fontes (HTML/JSON/texto) em `ExtractedEvent`; depende de `domain` (datas), nunca o contrário.

---

## Task 0: Setup do projeto (núcleo)

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/nightlife/__init__.py`, `src/nightlife/domain/__init__.py`, `src/nightlife/extraction/__init__.py`

- [ ] **Step 1: Criar a estrutura de pastas e os `__init__.py` vazios**

```bash
cd /d/MyProjects/nightlife-app
mkdir -p src/nightlife/domain src/nightlife/extraction tests
touch src/nightlife/__init__.py src/nightlife/domain/__init__.py src/nightlife/extraction/__init__.py
```

- [ ] **Step 2: Escrever `pyproject.toml`**

```toml
[project]
name = "nightlife"
version = "0.1.0"
description = "Nightlife/event discovery — domain core"
requires-python = ">=3.12"
dependencies = [
    "beautifulsoup4>=4.12",
    "tzdata>=2024.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 3: Escrever `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.env
*.egg-info/
build/
dist/
```

- [ ] **Step 4: Criar venv e instalar em modo editável**

```bash
cd /d/MyProjects/nightlife-app
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/python -m pip install -e ".[dev]"
```
Expected: instala `nightlife` (editable), `beautifulsoup4`, `tzdata`, `pytest` sem erro.

- [ ] **Step 5: Smoke test — pytest roda sem testes**

Run: `.venv/Scripts/python -m pytest`
Expected: `no tests ran` (exit 5) ou `collected 0 items` — sem erro de import/config.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore src/
git commit -m "chore: scaffold do nucleo de dominio (src layout + pytest)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 1: Normalização de datas PT-BR

**Files:**
- Create: `src/nightlife/domain/dates_ptbr.py`
- Test: `tests/test_dates_ptbr.py`

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_dates_ptbr.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

from nightlife.domain.dates_ptbr import parse_ptbr_datetime

SP = ZoneInfo("America/Sao_Paulo")
REF = date(2026, 6, 1)  # segunda-feira


def test_dd_mm_yyyy_is_exact():
    r = parse_ptbr_datetime("13/06/2026", reference=REF)
    assert r.dt == datetime(2026, 6, 13, 0, 0, tzinfo=SP)
    assert r.ambiguous is False


def test_dd_mm_without_year_infers_and_flags_ambiguous():
    r = parse_ptbr_datetime("festa dia 13/06", reference=REF)
    assert r.dt == datetime(2026, 6, 13, 0, 0, tzinfo=SP)
    assert r.ambiguous is True


def test_dd_mm_already_past_rolls_to_next_year():
    r = parse_ptbr_datetime("05/01", reference=REF)  # 5 jan < 1 jun -> proximo ano
    assert r.dt == datetime(2027, 1, 5, 0, 0, tzinfo=SP)
    assert r.ambiguous is True


def test_month_name_with_optional_de():
    r = parse_ptbr_datetime("13 de junho", reference=REF)
    assert r.dt.month == 6 and r.dt.day == 13
    r2 = parse_ptbr_datetime("SAB 13 JUN", reference=REF)
    assert r2.dt.month == 6 and r2.dt.day == 13


def test_weekday_next_occurrence():
    r = parse_ptbr_datetime("rola na sexta", reference=REF)  # ref=segunda -> sexta = +4
    assert r.dt == datetime(2026, 6, 5, 0, 0, tzinfo=SP)


def test_hoje_amanha():
    assert parse_ptbr_datetime("hoje", reference=REF).dt.day == 1
    assert parse_ptbr_datetime("amanha", reference=REF).dt.day == 2


def test_time_is_extracted():
    r = parse_ptbr_datetime("13/06 23h30", reference=REF)
    assert (r.dt.hour, r.dt.minute) == (23, 30)
    r2 = parse_ptbr_datetime("13/06 as 22h", reference=REF)
    assert (r2.dt.hour, r2.dt.minute) == (22, 0)


def test_no_date_returns_none():
    r = parse_ptbr_datetime("line-up insano sem data", reference=REF)
    assert r.dt is None
    assert r.matched is None


def test_invalid_date_returns_none():
    r = parse_ptbr_datetime("40/13/2026", reference=REF)
    assert r.dt is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_dates_ptbr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.domain.dates_ptbr'`.

- [ ] **Step 3: Implementar `dates_ptbr.py`**

```python
# src/nightlife/domain/dates_ptbr.py
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MESES = {
    "janeiro": 1, "jan": 1, "fevereiro": 2, "fev": 2, "marco": 3, "março": 3, "mar": 3,
    "abril": 4, "abr": 4, "maio": 5, "mai": 5, "junho": 6, "jun": 6, "julho": 7, "jul": 7,
    "agosto": 8, "ago": 8, "setembro": 9, "set": 9, "outubro": 10, "out": 10,
    "novembro": 11, "nov": 11, "dezembro": 12, "dez": 12,
}
# Monday=0 ... Sunday=6 (mais longos antes dos curtos para o regex casar certo)
DIAS = {
    "segunda": 0, "seg": 0, "terca": 1, "terça": 1, "ter": 1, "quarta": 2, "qua": 2,
    "quinta": 3, "qui": 3, "sexta": 4, "sex": 4, "sabado": 5, "sábado": 5, "sab": 5, "sáb": 5,
    "domingo": 6, "dom": 6,
}


@dataclass
class ParsedDate:
    dt: datetime | None        # tz-aware (America/Sao_Paulo) ou None
    ambiguous: bool            # True quando o ano foi inferido
    matched: str | None        # trecho reconhecido


def _norm(s: str) -> str:
    return s.strip().lower()


def _apply_time(d: date, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)


def _extract_time(text: str) -> tuple[int, int]:
    m = re.search(r"(\d{1,2})\s*(?:h|:)\s*(\d{2})?", text)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    return 0, 0


def parse_ptbr_datetime(text: str, *, reference: date, tz: str = "America/Sao_Paulo") -> ParsedDate:
    if not text or not text.strip():
        return ParsedDate(None, False, None)
    tzinfo = ZoneInfo(tz)
    t = _norm(text)
    hour, minute = _extract_time(t)

    if re.search(r"\bhoje\b", t):
        return ParsedDate(_apply_time(reference, hour, minute, tzinfo), False, "hoje")
    if re.search(r"\b(amanha|amanhã)\b", t):
        return ParsedDate(_apply_time(reference + timedelta(days=1), hour, minute, tzinfo), False, "amanhã")

    # dd/mm[/yyyy]
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        day, mon = int(m.group(1)), int(m.group(2))
        if m.group(3):
            yr = int(m.group(3))
            yr = yr + 2000 if yr < 100 else yr
            ambiguous = False
        else:
            yr, ambiguous = reference.year, True
        try:
            d = date(yr, mon, day)
        except ValueError:
            return ParsedDate(None, False, None)
        if ambiguous and d < reference:
            d = date(yr + 1, mon, day)
        return ParsedDate(_apply_time(d, hour, minute, tzinfo), ambiguous, m.group(0))

    # "13 [de] junho [de 2026]" / "13 jun"
    for m in re.finditer(r"\b(\d{1,2})\s+(?:de\s+)?([a-zç]{3,})(?:\s+de\s+(\d{4}))?\b", t):
        mon_word = _norm(m.group(2))
        if mon_word not in MESES:
            continue
        day, mon = int(m.group(1)), MESES[mon_word]
        if m.group(3):
            yr, ambiguous = int(m.group(3)), False
        else:
            yr, ambiguous = reference.year, True
        try:
            d = date(yr, mon, day)
        except ValueError:
            return ParsedDate(None, False, None)
        if ambiguous and d < reference:
            d = date(yr + 1, mon, day)
        return ParsedDate(_apply_time(d, hour, minute, tzinfo), ambiguous, m.group(0))

    # dia da semana -> proxima ocorrencia >= reference
    for word, wd in DIAS.items():
        if re.search(rf"\b{word}\b", t):
            delta = (wd - reference.weekday()) % 7
            d = reference + timedelta(days=delta)
            return ParsedDate(_apply_time(d, hour, minute, tzinfo), False, word)

    return ParsedDate(None, False, None)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_dates_ptbr.py -v`
Expected: PASS (todos os testes).

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/domain/dates_ptbr.py tests/test_dates_ptbr.py
git commit -m "feat(domain): normalizacao de datas PT-BR com timezone

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: Confidence scoring (venue + event)

**Files:**
- Create: `src/nightlife/domain/scoring.py`
- Test: `tests/test_scoring.py`

Pontuações exatamente como no spec §7. Penalidades têm valores definidos aqui (ajustáveis); score nunca fica negativo.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_scoring.py
from nightlife.domain.scoring import (
    VenueSignals, EventSignals, score_venue, score_event,
)


def test_venue_all_positive():
    s = VenueSignals(
        google_places_operational=True, osm_match=True, official_website=True,
        instagram_link=True, future_event_linked=True,
    )
    assert score_venue(s) == 30 + 20 + 20 + 15 + 15


def test_venue_individual_bonuses():
    assert score_venue(VenueSignals(google_places_operational=True)) == 30
    assert score_venue(VenueSignals(osm_match=True)) == 20
    assert score_venue(VenueSignals(official_website=True)) == 20
    assert score_venue(VenueSignals(instagram_link=True)) == 15
    assert score_venue(VenueSignals(future_event_linked=True)) == 15


def test_venue_penalties_and_clamp():
    s = VenueSignals(google_places_operational=True, permanently_closed=True)
    assert score_venue(s) == max(0, 30 - 50)  # clamp em 0
    assert score_venue(VenueSignals(unverified=True)) == 0


def test_event_all_positive():
    s = EventSignals(
        future_date=True, venue_matched=True, official_source=True,
        ticketing_source=True, independent_source_count=2,
    )
    assert score_event(s) == 20 + 20 + 25 + 25 + 20


def test_event_single_source_no_multisource_bonus():
    s = EventSignals(future_date=True, independent_source_count=1)
    assert score_event(s) == 20


def test_event_penalties_and_clamp():
    s = EventSignals(future_date=True, cancelled=True)
    assert score_event(s) == max(0, 20 - 50)
    assert score_event(EventSignals(past_date=True)) == 0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.domain.scoring'`.

- [ ] **Step 3: Implementar `scoring.py`**

```python
# src/nightlife/domain/scoring.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VenueSignals:
    google_places_operational: bool = False
    osm_match: bool = False
    official_website: bool = False
    instagram_link: bool = False
    future_event_linked: bool = False
    closed: bool = False
    permanently_closed: bool = False
    stale: bool = False
    unverified: bool = False


@dataclass
class EventSignals:
    future_date: bool = False
    venue_matched: bool = False
    official_source: bool = False        # site oficial do venue OU do organizador
    ticketing_source: bool = False
    independent_source_count: int = 1
    ambiguous_date: bool = False
    no_venue: bool = False
    past_date: bool = False
    cancelled: bool = False
    weak_source: bool = False


def score_venue(s: VenueSignals) -> int:
    score = 0
    if s.google_places_operational:
        score += 30
    if s.osm_match:
        score += 20
    if s.official_website:
        score += 20
    if s.instagram_link:
        score += 15
    if s.future_event_linked:
        score += 15
    if s.closed:
        score -= 20
    if s.permanently_closed:
        score -= 50
    if s.stale:
        score -= 10
    if s.unverified:
        score -= 15
    return max(0, score)


def score_event(s: EventSignals) -> int:
    score = 0
    if s.future_date:
        score += 20
    if s.venue_matched:
        score += 20
    if s.official_source:
        score += 25
    if s.ticketing_source:
        score += 25
    if s.independent_source_count >= 2:
        score += 20
    if s.ambiguous_date:
        score -= 10
    if s.no_venue:
        score -= 20
    if s.past_date:
        score -= 30
    if s.cancelled:
        score -= 50
    if s.weak_source:
        score -= 15
    return max(0, score)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_scoring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/domain/scoring.py tests/test_scoring.py
git commit -m "feat(domain): confidence scoring de venue e event

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: Venue matching

**Files:**
- Create: `src/nightlife/domain/matching.py`
- Test: `tests/test_matching.py`

`normalize_name` e `name_similarity` ficam aqui e são reusados por `dedupe.py` (Task 4).

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_matching.py
from nightlife.domain.matching import (
    VenueRef, normalize_name, name_similarity, match_venue,
)


def test_normalize_strips_accents_and_stopwords():
    assert normalize_name("Bar do Zé") == normalize_name("bar do ze")
    assert "bar" not in normalize_name("Bar do Zé").split()


def test_similarity_high_for_same_name():
    assert name_similarity("Lab Club", "lab club") > 0.95


def test_similarity_low_for_different_names():
    assert name_similarity("Lab Club", "Trackers") < 0.4


def test_match_returns_best_above_threshold():
    existing = [
        VenueRef(1, "Lab Club"),
        VenueRef(2, "Trackers"),
    ]
    m = match_venue(VenueRef(None, "lab club"), existing)
    assert m is not None and m.venue.id == 1


def test_no_match_below_threshold():
    existing = [VenueRef(1, "Lab Club")]
    assert match_venue(VenueRef(None, "Audio SP"), existing) is None


def test_geo_proximity_boosts_score():
    # nome sozinho fica abaixo do threshold; a coordenada quase identica desempata
    existing = [VenueRef(1, "Cargo", lat=-23.561, lng=-46.656)]
    m = match_venue(VenueRef(None, "Cargo SP", lat=-23.5611, lng=-46.6561), existing)
    assert m is not None and m.venue.id == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_matching.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.domain.matching'`.

- [ ] **Step 3: Implementar `matching.py`**

```python
# src/nightlife/domain/matching.py
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

_STOPWORDS = {"bar", "club", "clube", "casa", "the", "o", "a", "de", "do", "da"}


@dataclass
class VenueRef:
    id: int | None
    name: str
    address: str | None = None
    lat: float | None = None
    lng: float | None = None


@dataclass
class VenueMatch:
    venue: VenueRef
    score: float  # 0..1


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    tokens = [tok for tok in s.split() if tok not in _STOPWORDS]
    return " ".join(tokens)


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def match_venue(candidate: VenueRef, existing: list[VenueRef], *, threshold: float = 0.82) -> VenueMatch | None:
    best: VenueMatch | None = None
    for e in existing:
        s = name_similarity(candidate.name, e.name)
        if None not in (candidate.lat, candidate.lng, e.lat, e.lng):
            if _haversine_km(candidate.lat, candidate.lng, e.lat, e.lng) <= 0.15:
                s = min(1.0, s + 0.1)
        if best is None or s > best.score:
            best = VenueMatch(e, s)
    if best is not None and best.score >= threshold:
        return best
    return None
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_matching.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/domain/matching.py tests/test_matching.py
git commit -m "feat(domain): venue matching por nome normalizado + geo

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 4: Deduplicação de eventos

**Files:**
- Create: `src/nightlife/domain/dedupe.py`
- Test: `tests/test_dedupe.py`

Combina similaridade de nome, proximidade de data/hora e similaridade de venue; `ticket_url` igual é sinal forte; organizer igual reforça. `classify` decide auto_merge / review / distinct. Recorrências (mesma festa em datas distantes) caem em `distinct`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_dedupe.py
from datetime import datetime
from zoneinfo import ZoneInfo

from nightlife.domain.dedupe import EventKey, dedupe_score, classify, compare

SP = ZoneInfo("America/Sao_Paulo")


def _ev(name, dt, venue=None, organizer=None, ticket=None):
    return EventKey(name=name, starts_at=dt, venue_name=venue, organizer=organizer, ticket_url=ticket)


def test_same_event_auto_merges():
    a = _ev("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), venue="Lab Club")
    b = _ev("MAMBA NEGRA", datetime(2026, 6, 13, 23, 30, tzinfo=SP), venue="lab club")
    assert classify(dedupe_score(a, b)) == "auto_merge"


def test_same_ticket_url_forces_auto_merge():
    a = _ev("Festa X", datetime(2026, 6, 13, 23, 0, tzinfo=SP), ticket="https://sympla.com.br/e/123")
    b = _ev("Evento Y", datetime(2026, 6, 13, 22, 0, tzinfo=SP), ticket="https://sympla.com.br/e/123")
    assert classify(dedupe_score(a, b)) == "auto_merge"


def test_distinct_events():
    a = _ev("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), venue="Lab Club")
    b = _ev("Carlos Capslock", datetime(2026, 7, 20, 23, 0, tzinfo=SP), venue="Audio")
    assert classify(dedupe_score(a, b)) == "distinct"


def test_recurring_party_same_name_far_dates_is_distinct():
    a = _ev("Gop Tun", datetime(2026, 6, 7, 16, 0, tzinfo=SP), venue="Cargo")
    b = _ev("Gop Tun", datetime(2026, 6, 14, 16, 0, tzinfo=SP), venue="Cargo")  # +7 dias
    assert classify(dedupe_score(a, b)) == "distinct"


def test_compare_returns_result_object():
    a = _ev("Festa", datetime(2026, 6, 13, 23, 0, tzinfo=SP), venue="Lab")
    b = _ev("Festa", datetime(2026, 6, 13, 23, 0, tzinfo=SP), venue="Lab")
    r = compare(a, b)
    assert r.decision == "auto_merge" and r.score >= 0.9
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_dedupe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.domain.dedupe'`.

- [ ] **Step 3: Implementar `dedupe.py`**

```python
# src/nightlife/domain/dedupe.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .matching import name_similarity, normalize_name


@dataclass
class EventKey:
    name: str
    starts_at: datetime | None
    venue_name: str | None = None
    organizer: str | None = None
    ticket_url: str | None = None


@dataclass
class DedupeResult:
    score: float
    decision: str  # "auto_merge" | "review" | "distinct"


def _date_proximity(a: datetime | None, b: datetime | None) -> float:
    if a is None or b is None:
        return 0.0
    diff = abs((a - b).total_seconds())
    if diff <= 3600:
        return 1.0
    if diff <= 6 * 3600:
        return 0.7
    if diff <= 24 * 3600:
        return 0.4
    return 0.0


def dedupe_score(a: EventKey, b: EventKey) -> float:
    name = name_similarity(a.name, b.name)
    date = _date_proximity(a.starts_at, b.starts_at)
    if a.venue_name and b.venue_name:
        venue = name_similarity(a.venue_name, b.venue_name)
    else:
        venue = 0.0
    same_ticket = bool(a.ticket_url and b.ticket_url and a.ticket_url == b.ticket_url)

    score = 0.5 * name + 0.3 * date + 0.2 * venue
    # Sem proximidade de data (e sem ticket igual), no maximo "distinto":
    # evita tratar recorrencias (mesma festa em datas distantes) como duplicata.
    if date == 0.0 and not same_ticket:
        score = min(score, 0.6)
    if same_ticket:
        score = max(score, 0.95)
    if a.organizer and b.organizer and normalize_name(a.organizer) == normalize_name(b.organizer):
        score = min(1.0, score + 0.1)
    return score


def classify(score: float) -> str:
    if score >= 0.9:
        return "auto_merge"
    if score >= 0.65:
        return "review"
    return "distinct"


def compare(a: EventKey, b: EventKey) -> DedupeResult:
    s = dedupe_score(a, b)
    return DedupeResult(s, classify(s))
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_dedupe.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/domain/dedupe.py tests/test_dedupe.py
git commit -m "feat(domain): dedupe de eventos com gate de proximidade de data

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 5: Extração JSON-LD Schema.org Event

**Files:**
- Create: `src/nightlife/extraction/base.py`
- Create: `src/nightlife/extraction/jsonld.py`
- Test: `tests/test_jsonld.py`

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_jsonld.py
from nightlife.extraction.jsonld import parse_jsonld_events

PAGE_SINGLE = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Event","name":"Mamba Negra",
 "startDate":"2026-06-13T23:00:00-03:00",
 "location":{"@type":"Place","name":"Lab Club"},
 "offers":{"@type":"Offer","url":"https://sympla.com.br/e/mamba"}}
</script></head><body></body></html>
"""

PAGE_GRAPH = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebSite","name":"Agenda"},
  {"@type":["Event","MusicEvent"],"name":"Carlos Capslock","startDate":"2026-07-20T22:00:00-03:00"}
]}
</script></head><body></body></html>
"""

PAGE_NONE = "<html><body><p>sem dados estruturados</p></body></html>"
PAGE_BROKEN = '<script type="application/ld+json">{not valid json,,}</script>'


def test_parses_single_event():
    evs = parse_jsonld_events(PAGE_SINGLE, source_url="http://x")
    assert len(evs) == 1
    e = evs[0]
    assert e.name == "Mamba Negra"
    assert e.venue_name == "Lab Club"
    assert e.ticket_url == "https://sympla.com.br/e/mamba"
    assert e.starts_at is not None and e.starts_at.hour == 23
    assert e.source_url == "http://x"


def test_parses_event_inside_graph_and_type_list():
    evs = parse_jsonld_events(PAGE_GRAPH)
    assert [e.name for e in evs] == ["Carlos Capslock"]


def test_no_jsonld_returns_empty():
    assert parse_jsonld_events(PAGE_NONE) == []


def test_broken_jsonld_is_ignored():
    assert parse_jsonld_events(PAGE_BROKEN) == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_jsonld.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.extraction.jsonld'`.

- [ ] **Step 3: Implementar `base.py` e `jsonld.py`**

```python
# src/nightlife/extraction/base.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ExtractedEvent:
    name: str | None = None
    starts_at_raw: str | None = None
    starts_at: datetime | None = None
    ends_at_raw: str | None = None
    venue_name: str | None = None
    address: str | None = None
    organizer: str | None = None
    lineup_text: str | None = None
    genre: str | None = None
    ticket_url: str | None = None
    price_raw: str | None = None
    source_url: str | None = None
    raw: dict = field(default_factory=dict)
    field_confidence: dict = field(default_factory=dict)
```

```python
# src/nightlife/extraction/jsonld.py
from __future__ import annotations

import json
from datetime import datetime

from bs4 import BeautifulSoup

from .base import ExtractedEvent


def _iter_jsonld(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = tag.get_text()
        if not text or not text.strip():
            continue
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            yield from data
        elif isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                yield from graph
            else:
                yield data


def _is_event(node) -> bool:
    if not isinstance(node, dict):
        return False
    t = node.get("@type")
    if isinstance(t, list):
        return any("Event" in str(x) for x in t)
    return isinstance(t, str) and "Event" in t


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _location_name(node):
    loc = node.get("location")
    if isinstance(loc, dict):
        return loc.get("name")
    if isinstance(loc, list) and loc and isinstance(loc[0], dict):
        return loc[0].get("name")
    if isinstance(loc, str):
        return loc
    return None


def _offers_url(node):
    off = node.get("offers")
    if isinstance(off, dict):
        return off.get("url")
    if isinstance(off, list) and off and isinstance(off[0], dict):
        return off[0].get("url")
    return None


def parse_jsonld_events(html: str, *, source_url: str | None = None) -> list[ExtractedEvent]:
    out: list[ExtractedEvent] = []
    for node in _iter_jsonld(html):
        if not _is_event(node):
            continue
        out.append(
            ExtractedEvent(
                name=node.get("name"),
                starts_at_raw=node.get("startDate"),
                starts_at=_parse_iso(node.get("startDate")),
                ends_at_raw=node.get("endDate"),
                venue_name=_location_name(node),
                ticket_url=_offers_url(node),
                source_url=source_url,
                raw=node,
            )
        )
    return out
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_jsonld.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/extraction/base.py src/nightlife/extraction/jsonld.py tests/test_jsonld.py
git commit -m "feat(extraction): parser de JSON-LD Schema.org Event

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 6: HTML patterns + extração de texto livre (fallback determinístico)

**Files:**
- Create: `src/nightlife/extraction/html_patterns.py`
- Create: `src/nightlife/extraction/freetext.py`
- Test: `tests/test_extraction_text.py`

`freetext` é a **interface de extração de texto livre com fallback determinístico** do spec §8: mesma assinatura que um extractor via LLM terá no futuro, mas aqui 100% determinístico (sem rede).

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_extraction_text.py
from datetime import date

from nightlife.extraction.html_patterns import parse_html_patterns
from nightlife.extraction.freetext import extract_freetext_deterministic

REF = date(2026, 6, 1)

FLYER_TEXT = """MAMBA NEGRA
SEX 13/06 a partir das 23h
Lab Club - São Paulo
ingressos: https://sympla.com.br/e/mamba
"""

HTML_MICRODATA = """
<div itemscope itemtype="https://schema.org/Event">
  <span itemprop="name">Carlos Capslock</span>
  <meta itemprop="startDate" content="2026-07-20T22:00:00-03:00">
</div>
"""


def test_freetext_extracts_name_date_and_ticket():
    ev = extract_freetext_deterministic(FLYER_TEXT, reference=REF, source_url="http://ig/x")
    assert ev.name == "MAMBA NEGRA"
    assert ev.starts_at is not None and ev.starts_at.day == 13 and ev.starts_at.hour == 23
    assert ev.ticket_url == "https://sympla.com.br/e/mamba"
    assert ev.source_url == "http://ig/x"
    assert ev.field_confidence.get("starts_at") == 0.5  # dia/mes sem ano => ambiguo


def test_freetext_without_date_has_no_starts_at():
    ev = extract_freetext_deterministic("apenas um nome de festa", reference=REF)
    assert ev.starts_at is None


def test_html_microdata_event():
    evs = parse_html_patterns(HTML_MICRODATA, source_url="http://site")
    assert len(evs) == 1
    assert evs[0].name == "Carlos Capslock"
    assert evs[0].starts_at_raw == "2026-07-20T22:00:00-03:00"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_extraction_text.py -v`
Expected: FAIL — `ModuleNotFoundError` para `html_patterns` / `freetext`.

- [ ] **Step 3: Implementar `freetext.py` e `html_patterns.py`**

```python
# src/nightlife/extraction/freetext.py
from __future__ import annotations

import re
from datetime import date

from ..domain.dates_ptbr import parse_ptbr_datetime
from .base import ExtractedEvent


def extract_freetext_deterministic(
    text: str, *, reference: date, source_url: str | None = None
) -> ExtractedEvent:
    ev = ExtractedEvent(source_url=source_url, raw={"text": text})

    pd = parse_ptbr_datetime(text, reference=reference)
    ev.starts_at = pd.dt
    ev.starts_at_raw = pd.matched
    if pd.dt is not None:
        ev.field_confidence["starts_at"] = 0.5 if pd.ambiguous else 0.9

    for line in text.splitlines():
        if line.strip():
            ev.name = line.strip()
            break

    m = re.search(r"https?://\S+", text)
    if m:
        ev.ticket_url = m.group(0)

    return ev
```

```python
# src/nightlife/extraction/html_patterns.py
from __future__ import annotations

from bs4 import BeautifulSoup

from .base import ExtractedEvent


def _has_event_type(value) -> bool:
    return bool(value) and "Event" in value


def parse_html_patterns(html: str, *, source_url: str | None = None) -> list[ExtractedEvent]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[ExtractedEvent] = []
    for node in soup.find_all(attrs={"itemtype": _has_event_type}):
        name_el = node.find(attrs={"itemprop": "name"})
        start_el = node.find(attrs={"itemprop": "startDate"})
        starts_raw = None
        if start_el is not None:
            starts_raw = start_el.get("content") or start_el.get_text(strip=True)
        out.append(
            ExtractedEvent(
                name=name_el.get_text(strip=True) if name_el else None,
                starts_at_raw=starts_raw,
                source_url=source_url,
            )
        )
    return out
```

- [ ] **Step 4: Rodar e ver passar (suíte inteira)**

Run: `.venv/Scripts/python -m pytest -v`
Expected: PASS — todos os arquivos de teste (6) verdes.

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/extraction/html_patterns.py src/nightlife/extraction/freetext.py tests/test_extraction_text.py
git commit -m "feat(extraction): HTML microdata + texto livre (fallback deterministico)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Coverage map (Plano A ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §13 datas PT-BR | Task 1 |
| §13 confidence score | Task 2 |
| §13 venue matching | Task 3 |
| §13 dedupe de eventos | Task 4 |
| §13 JSON-LD Event | Task 5 |
| §8 JSON-LD + HTML + texto livre c/ fallback determinístico | Tasks 5, 6 |
| §7 pontuações exatas venue/event | Task 2 |
| §9 normalização de nomes + similaridade + proximidade de data + organizer/ticket | Tasks 3, 4 |

**Fora do Plano A (vai pro Plano B):** modelo de dados/migrations, evidência persistida (`*_sources`, `raw_payload_hash`, `last_seen_at`), `ingestion_runs`, pipeline mock end-to-end, API FastAPI, métricas de coverage/freshness, README. Itens "futuros" do spec (vision multimodal real + pHash + OCR, Playwright/IG, Telegram, Places/OSM/ticketing reais, telas) ficam para planos seguintes.
