# Nightlife App — Plano F: Fonte Sympla (eventos estruturados) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trazer eventos reais de festas/shows de São Paulo via a API de busca da Sympla — com venue embutido (geo), organizer linkado como cidadão de primeira classe, e o débito de timezone (dia = America/Sao_Paulo) resolvido.

**Architecture:** Spec: `docs/superpowers/specs/2026-07-03-sympla-source-design.md`. O protocolo `Source` ganha `events() -> Iterable[RawEvent]` (evento estruturado com `RawVenue` embutido); o pipeline ganha um terceiro loop (venue embutido → organizer → evento). `parse_search_records` é pura (fixture offline); `SymplaSource` pagina o `POST /api/v1/search` com filtro client-side garantido (cidade + tema + futuro).

**Tech Stack:** Python 3.14 · SQLAlchemy 2.0 · httpx + truststore · pytest. Postgres na 5434 (Docker).

**Convenções:**
- `.venv/Scripts/python -m ...`; cwd RESETA entre chamadas Bash — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Testes de DB: `docker compose up -d --wait`. Contagem: `-o console_output_style=count -p no:warnings` (sem pipe pra grep/tail).
- Suíte atual: **79 passed**. Commits terminam com: `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`
- **NÃO modifique** `config.py`, `docker-compose.yml`, `tests/conftest.py`, `.env.example`, `migrations/`, `models.py`, `domain/` (exceto nada), `api/`.

---

## File Structure

```
src/nightlife/
  ingestion/
    base.py              # + RawEvent, Source.events()  (Task 0)
    mock_source.py       # + events opcional  (Task 0)
    osm_source.py        # + events() -> []  (Task 0)
    pipeline.py          # 3o loop  (Task 3)
    sympla_source.py     # parse_search_records + SymplaSource  (Task 4)
  persistence/
    confidence.py        # dia = America/Sao_Paulo  (Task 1)
    inputs.py            # EventInput.organizer_id  (Task 2)
    organizers.py        # get_or_create_organizer  (Task 2)
    events_repo.py       # organizer_id no create + gap-fill  (Task 2)
  ingest_sympla.py       # runner  (Task 5)
tests/
  test_mock_source.py (T0) · test_osm_source.py (T0) · test_confidence.py (T1)
  test_organizers.py (T2) · test_pipeline.py (T3) · test_sympla_source.py (T4)
README.md (T5)
```

---

## Task 0: `RawEvent` + `Source.events()` (protocolo)

**Files:**
- Modify: `src/nightlife/ingestion/base.py`, `src/nightlife/ingestion/mock_source.py`, `src/nightlife/ingestion/osm_source.py`
- Test: `tests/test_mock_source.py` (append), `tests/test_osm_source.py` (editar 1 teste)

- [ ] **Step 1: Testes que falham**

Append em `tests/test_mock_source.py`:

```python
def test_mock_source_events_default_empty_and_settable():
    from nightlife.ingestion.base import RawEvent

    assert MockSource([], []).events() == []
    rev = RawEvent(name="Festa X", source_type="ticketing")
    assert MockSource([], [], events=[rev]).events() == [rev]
```

Em `tests/test_osm_source.py`, substitua o teste `test_osm_source_event_pages_is_empty` por:

```python
def test_osm_source_events_and_pages_are_empty():
    src = OSMSource()
    assert src.event_pages() == []
    assert src.events() == []
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_mock_source.py tests/test_osm_source.py -q`
Expected: FAIL — `ImportError: cannot import name 'RawEvent'` e/ou `AttributeError: ... 'events'`.

- [ ] **Step 3: Implementar**

Em `src/nightlife/ingestion/base.py`, substitua o conteúdo inteiro por:

```python
# src/nightlife/ingestion/base.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Protocol


@dataclass
class RawVenue:
    name: str
    source_type: str
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    category: str | None = None
    source_url: str | None = None
    raw_payload: str = ""


@dataclass
class RawEventPage:
    kind: str          # "jsonld" | "html" | "freetext"
    content: str
    source_type: str
    source_url: str | None = None


@dataclass
class RawEvent:
    """Evento JA estruturado (ex.: API de ticketing) — dispensa extracao.

    O venue vem EMBUTIDO (nome/endereco/geo) para o pipeline upsertar e ancorar.
    """
    name: str
    source_type: str                    # "ticketing"
    starts_at: datetime | None = None   # tz-aware (UTC da API)
    ends_at: datetime | None = None
    venue: RawVenue | None = None
    organizer_name: str | None = None
    genre: str | None = None
    ticket_url: str | None = None
    source_url: str | None = None
    raw_payload: str = ""


class Source(Protocol):
    def venues(self) -> Iterable[RawVenue]: ...
    def event_pages(self) -> Iterable[RawEventPage]: ...
    def events(self) -> Iterable[RawEvent]: ...
```

Em `src/nightlife/ingestion/mock_source.py`, substitua a classe inteira por:

```python
class MockSource:
    """Fonte de teste que serve registros a partir de listas em memoria ou de fixtures JSON."""

    def __init__(self, venues: list[RawVenue], event_pages: list[RawEventPage],
                 events: list["RawEvent"] | None = None) -> None:
        self._venues = venues
        self._pages = event_pages
        self._events = events or []

    @classmethod
    def from_fixtures(cls, venues_path: Path | str, event_pages_path: Path | str) -> MockSource:
        venues = [RawVenue(**d) for d in json.loads(Path(venues_path).read_text(encoding="utf-8"))]
        pages = [RawEventPage(**d) for d in json.loads(Path(event_pages_path).read_text(encoding="utf-8"))]
        return cls(venues, pages)

    def venues(self) -> list[RawVenue]:
        return list(self._venues)

    def event_pages(self) -> list[RawEventPage]:
        return list(self._pages)

    def events(self) -> list["RawEvent"]:
        return list(self._events)
```

E ajuste o import no topo do arquivo para `from .base import RawEvent, RawEventPage, RawVenue`.

Em `src/nightlife/ingestion/osm_source.py`, ajuste o import para `from .base import RawEvent, RawEventPage, RawVenue` e adicione ao FINAL da classe `OSMSource`:

```python
    def events(self) -> list[RawEvent]:
        return []
```

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_mock_source.py tests/test_osm_source.py -q`
Expected: PASS (5 testes). Suíte inteira: **80**.

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/base.py src/nightlife/ingestion/mock_source.py src/nightlife/ingestion/osm_source.py tests/test_mock_source.py tests/test_osm_source.py && git commit -m "feat(ingestion): RawEvent + Source.events() (eventos estruturados)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 1: Dia = America/Sao_Paulo em `confidence.py`

**Files:**
- Modify: `src/nightlife/persistence/confidence.py`
- Test: `tests/test_confidence.py` (append)

- [ ] **Step 1: Teste que falha** — append em `tests/test_confidence.py`:

```python
def test_future_past_uses_sao_paulo_day(session):
    from datetime import timezone

    from nightlife.persistence.confidence import event_signals_from_evidence

    v = Venue(name="X")
    session.add(v)
    session.flush()
    # sabado 06/06/2026 23:00 em SP == domingo 07/06 02:00 UTC
    e = Event(name="Madrugada", venue_id=v.id,
              starts_at=datetime(2026, 6, 7, 2, 0, tzinfo=timezone.utc))
    session.add(e)
    session.flush()
    record_event_evidence(session, e.id, _src("ticketing", "https://t/x"), contribution=25)

    # referencia = domingo 07/06: no dia SP o evento foi SABADO -> passado
    sig = event_signals_from_evidence(session, e, reference=date(2026, 6, 7))
    assert sig.past_date is True and sig.future_date is False
    # referencia = sabado 06/06: mesmo dia SP -> futuro
    sig2 = event_signals_from_evidence(session, e, reference=date(2026, 6, 6))
    assert sig2.future_date is True and sig2.past_date is False
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_confidence.py -q`
Expected: FAIL — o primeiro assert quebra (`.date()` em UTC dá 07/06 >= 07/06 → future).

- [ ] **Step 3: Implementar** — em `src/nightlife/persistence/confidence.py`:

Adicione após os imports existentes:

```python
from zoneinfo import ZoneInfo

# "Dia" do sistema = dia em America/Sao_Paulo (spec sympla §6). A API da
# Sympla entrega UTC; sem converter, festa de sabado 23h viraria "domingo".
_SP_TZ = ZoneInfo("America/Sao_Paulo")
```

E em `event_signals_from_evidence`, substitua:

```python
        future_date=starts is not None and starts.date() >= reference,
```
por
```python
        future_date=starts is not None and starts.astimezone(_SP_TZ).date() >= reference,
```
e
```python
        past_date=starts is not None and starts.date() < reference,
```
por
```python
        past_date=starts is not None and starts.astimezone(_SP_TZ).date() < reference,
```

(O pré-filtro SQL de `future_event_linked` e o da API mantêm o cast UTC — tolerância de ±3h na virada, documentada no spec.)

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_confidence.py -q`
Expected: PASS (3 testes). Suíte inteira: **81**.

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/persistence/confidence.py tests/test_confidence.py && git commit -m "fix(persistence): dia do sistema = America/Sao_Paulo (festa de sabado 23h e sabado)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: Organizer de primeira classe

**Files:**
- Create: `src/nightlife/persistence/organizers.py`
- Modify: `src/nightlife/persistence/inputs.py` (1 linha), `src/nightlife/persistence/events_repo.py` (2 linhas)
- Test: `tests/test_organizers.py`

- [ ] **Step 1: Teste que falha** — create `tests/test_organizers.py`:

```python
# tests/test_organizers.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nightlife.models import Organizer, Venue
from nightlife.persistence.events_repo import upsert_event
from nightlife.persistence.inputs import EventInput, SourceInfo
from nightlife.persistence.organizers import get_or_create_organizer

SP = ZoneInfo("America/Sao_Paulo")
REF = date(2026, 6, 1)


def test_get_or_create_reuses_by_normalized_name(session):
    a = get_or_create_organizer(session, "Mamba Org")
    b = get_or_create_organizer(session, "mamba org")
    assert a.id == b.id
    assert len(session.scalars(select(Organizer)).all()) == 1


def test_event_links_and_gapfills_organizer(session):
    v = Venue(name="Lab Club")
    session.add(v)
    session.flush()
    org = get_or_create_organizer(session, "Mamba Org")

    e = upsert_event(
        session,
        EventInput(name="Mamba Negra", starts_at=datetime(2026, 6, 13, 23, 0, tzinfo=SP),
                   venue_id=v.id, venue_name=v.name, organizer="Mamba Org", organizer_id=org.id),
        SourceInfo(source_type="ticketing", source_url="http://t", raw_payload="p", extracted_fields={}),
        reference=REF,
    )
    assert e.organizer_id == org.id

    # merge vindo de outra fonte SEM organizer_id nao apaga o link (gap-fill)
    e2 = upsert_event(
        session,
        EventInput(name="MAMBA NEGRA", starts_at=datetime(2026, 6, 13, 23, 30, tzinfo=SP),
                   venue_id=v.id, venue_name=v.name),
        SourceInfo(source_type="instagram", source_url="http://ig", raw_payload="p", extracted_fields={}),
        reference=REF,
    )
    assert e2.id == e.id and e2.organizer_id == org.id
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_organizers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.persistence.organizers'`.

- [ ] **Step 3: Implementar**

Create `src/nightlife/persistence/organizers.py`:

```python
# src/nightlife/persistence/organizers.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.matching import normalize_name
from ..models import Organizer


def get_or_create_organizer(session: Session, name: str) -> Organizer:
    """Organizer e cidadao de primeira classe: reusa por nome normalizado
    (mesmo padrao O(n) do esqueleto), cria se nao existe."""
    wanted = normalize_name(name)
    for org in session.scalars(select(Organizer)).all():
        if normalize_name(org.name) == wanted:
            return org
    org = Organizer(name=name)
    session.add(org)
    session.flush()
    return org
```

Em `src/nightlife/persistence/inputs.py`, no `EventInput`, logo após `organizer: str | None = None`, adicione:

```python
    organizer_id: int | None = None
```

Em `src/nightlife/persistence/events_repo.py`:
- no branch de **auto_merge**, junto dos outros gap-fills, adicione:
```python
        event.organizer_id = event.organizer_id if event.organizer_id is not None else candidate.organizer_id
```
- no branch de **criação**, no construtor `Event(...)`, adicione `organizer_id=candidate.organizer_id,` (após `venue_id=candidate.venue_id,`).

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_organizers.py tests/test_events_repo.py -q`
Expected: PASS (7 testes). Suíte inteira: **83**.

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/persistence/organizers.py src/nightlife/persistence/inputs.py src/nightlife/persistence/events_repo.py tests/test_organizers.py && git commit -m "feat(persistence): organizer de primeira classe (get_or_create + organizer_id linkado)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: Pipeline — terceiro loop (`events()`)

**Files:**
- Modify: `src/nightlife/ingestion/pipeline.py`
- Test: `tests/test_pipeline.py` (append)

- [ ] **Step 1: Teste que falha** — append em `tests/test_pipeline.py`:

```python
def test_pipeline_ingests_structured_events(session):
    from datetime import datetime, timezone

    from nightlife.ingestion.base import RawEvent
    from nightlife.models import Organizer

    rv = RawVenue(name="Lab Club", source_type="ticketing", lat=-23.56, lng=-46.65)
    rev = RawEvent(name="Mamba Negra", source_type="ticketing",
                   starts_at=datetime(2099, 6, 14, 2, 0, tzinfo=timezone.utc),
                   venue=rv, organizer_name="Mamba Org", genre="Festa",
                   ticket_url="https://sympla/e/1", source_url="https://sympla/e/1",
                   raw_payload="{}")
    src = MockSource([], [], events=[rev])
    run = run_ingestion(session, src, reference=REF)
    session.flush()

    assert run.records_found == 1 and run.records_created == 1
    v = session.scalars(select(Venue)).one()
    assert v.name == "Lab Club" and v.lat == -23.56
    e = session.scalars(select(Event)).one()
    assert e.venue_id == v.id and e.genre == "Festa" and e.ticket_url == "https://sympla/e/1"
    org = session.scalars(select(Organizer)).one()
    assert e.organizer_id == org.id and org.name == "Mamba Org"
    assert e.confidence == 20 + 20 + 25  # future + venue + ticketing
    assert v.confidence == 15            # future_event_linked (ticketing contribui 0 no venue)
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_pipeline.py -q`
Expected: FAIL — `records_found == 0` (o pipeline ignora `events()`).

- [ ] **Step 3: Implementar** — em `src/nightlife/ingestion/pipeline.py`:

Adicione o import `from ..persistence.organizers import get_or_create_organizer` junto dos demais imports de persistence.

No bloco try do fetch, adicione a terceira linha:

```python
    try:
        raw_venues = list(source.venues())
        raw_pages = list(source.event_pages())
        raw_events = list(source.events())
```

E, após o loop de `raw_pages` (antes de `run.status = "finished"`), adicione:

```python
    for rev in raw_events:
        found += 1
        try:
            venue = None
            if rev.venue is not None:
                venue = upsert_venue(
                    session,
                    VenueInput(name=rev.venue.name, lat=rev.venue.lat, lng=rev.venue.lng,
                               address=rev.venue.address, category=rev.venue.category),
                    SourceInfo(source_type=rev.source_type, source_url=rev.source_url,
                               raw_payload=rev.raw_payload),
                    reference=reference,
                )
            organizer_id = None
            if rev.organizer_name:
                organizer_id = get_or_create_organizer(session, rev.organizer_name).id
            upsert_event(
                session,
                EventInput(
                    name=rev.name, starts_at=rev.starts_at, ends_at=rev.ends_at,
                    venue_id=venue.id if venue is not None else None,
                    venue_name=rev.venue.name if rev.venue is not None else None,
                    organizer=rev.organizer_name, organizer_id=organizer_id,
                    genre=rev.genre, ticket_url=rev.ticket_url,
                    raw_fields={"raw": rev.raw_payload},
                ),
                SourceInfo(source_type=rev.source_type, source_url=rev.source_url,
                           raw_payload=rev.raw_payload),
                reference=reference,
            )
            created += 1
        except Exception as exc:  # noqa: BLE001 — registra o evento e segue
            errors.append(f"structured event {rev.name!r}: {exc}")
```

- [ ] **Step 4: Ver passar (suíte inteira)**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest -q -o console_output_style=count -p no:warnings`
Expected: **84 passed** (`[84/84]`).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/pipeline.py tests/test_pipeline.py && git commit -m "feat(ingestion): pipeline processa eventos estruturados (venue embutido + organizer)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 4: `sympla_source.py` (parse puro + fonte)

**Files:**
- Create: `src/nightlife/ingestion/sympla_source.py`
- Test: `tests/test_sympla_source.py`

- [ ] **Step 1: Teste que falha** — create `tests/test_sympla_source.py`:

```python
# tests/test_sympla_source.py
from datetime import date

from nightlife.ingestion.sympla_source import SymplaSource, parse_search_records

REF = date(2026, 6, 1)

SEARCH_JSON = {
    "data": [
        {  # festa em SP futura -> ENTRA
            "id": 111, "name": "Mamba Negra", "city": "São Paulo", "state": "SP",
            "theme_name": "Festas e Shows", "collection_name": ["FESTA E SHOW"],
            "format_name": "Festa",
            "url": "https://www.sympla.com.br/evento/mamba/111",
            "start_date_utc": "2099-06-14T02:00:00+00:00",
            "end_date_utc": "2099-06-14T09:00:00+00:00",
            "location": {"name": "Lab Club", "address": "R. Augusta, 1000",
                         "city": "São Paulo", "state": "SP",
                         "lat": -23.5613, "lon": -46.6565},
            "organizer": {"id": "77", "name": "Mamba Org"},
        },
        {  # outra cidade -> FORA
            "id": 222, "name": "Festa Carioca", "city": "Rio de Janeiro", "state": "RJ",
            "theme_name": "Festas e Shows", "collection_name": ["FESTA E SHOW"],
            "start_date_utc": "2099-06-14T02:00:00+00:00",
        },
        {  # tema errado -> FORA
            "id": 333, "name": "Curso de RCP", "city": "São Paulo", "state": "SP",
            "theme_name": "Cursos e Workshops", "collection_name": [],
            "start_date_utc": "2099-06-14T02:00:00+00:00",
        },
        {  # sem name -> FORA
            "id": 444, "city": "São Paulo", "theme_name": "Festas e Shows",
        },
        {  # passado -> FORA
            "id": 555, "name": "Festa Antiga", "city": "São Paulo", "state": "SP",
            "theme_name": "Festas e Shows", "collection_name": ["FESTA E SHOW"],
            "start_date_utc": "2020-01-01T02:00:00+00:00",
        },
    ]
}


def test_parse_search_records_filters_and_maps():
    revs = parse_search_records(SEARCH_JSON, reference=REF)
    assert [r.name for r in revs] == ["Mamba Negra"]
    r = revs[0]
    assert r.source_type == "ticketing"
    assert r.venue is not None and r.venue.name == "Lab Club"
    assert r.venue.lat == -23.5613 and r.venue.lng == -46.6565
    assert r.venue.source_type == "ticketing"
    assert r.organizer_name == "Mamba Org"
    assert r.genre == "Festa"
    assert r.ticket_url == "https://www.sympla.com.br/evento/mamba/111"
    assert r.starts_at is not None and r.starts_at.tzinfo is not None
    assert r.ends_at is not None


def test_sympla_source_other_methods_empty():
    src = SymplaSource()
    assert src.venues() == []
    assert src.event_pages() == []
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_sympla_source.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.ingestion.sympla_source'`.

- [ ] **Step 3: Implementar** — create `src/nightlife/ingestion/sympla_source.py`:

```python
# src/nightlife/ingestion/sympla_source.py
from __future__ import annotations

import json
from datetime import date
from zoneinfo import ZoneInfo

import httpx

from ..extraction.base import parse_iso
from .base import RawEvent, RawEventPage, RawVenue

SYMPLA_SEARCH_ENDPOINT = "https://www.sympla.com.br/api/v1/search"
_USER_AGENT = "nightlife-app/0.1 (uso pessoal; contato: henrique.rachti@gmail.com)"
_SP_TZ = ZoneInfo("America/Sao_Paulo")

# Escopo (spec sympla §2, opcao b do usuario): tema "Festas e Shows" inteiro.
# Valores observados na API real em 2026-07-03; a colecao e o cinto-e-suspensorio.
_CITY = "São Paulo"
_PARTY_THEME = "Festas e Shows"
_PARTY_COLLECTION = "FESTA E SHOW"


def _wanted(record: dict) -> bool:
    if (record.get("city") or "").strip() != _CITY:
        return False
    theme = (record.get("theme_name") or "").strip()
    collections = record.get("collection_name") or []
    return theme == _PARTY_THEME or _PARTY_COLLECTION in collections


def parse_search_records(data: dict, *, reference: date) -> list[RawEvent]:
    """Registros da API de busca da Sympla -> RawEvents. Puro: testavel offline.

    Filtro client-side GARANTIDO (o server-side e best-effort): cidade =
    Sao Paulo, tema festas/shows, e so eventos de hoje (dia SP) em diante.
    Descarta registros sem name.
    """
    out: list[RawEvent] = []
    for rec in data.get("data") or []:
        name = rec.get("name")
        if not name or not _wanted(rec):
            continue
        starts = parse_iso(rec.get("start_date_utc") or rec.get("start_date"))
        if starts is not None and starts.astimezone(_SP_TZ).date() < reference:
            continue  # so futuros (dia SP)
        ends = parse_iso(rec.get("end_date_utc") or rec.get("end_date"))
        loc = rec.get("location") or {}
        venue = None
        if loc.get("name"):
            venue = RawVenue(
                name=loc["name"],
                source_type="ticketing",
                lat=loc.get("lat"),
                lng=loc.get("lon"),
                address=(loc.get("address") or "").strip() or None,
                category=None,
                source_url=rec.get("url"),
            )
        organizer = rec.get("organizer") or {}
        out.append(RawEvent(
            name=name,
            source_type="ticketing",
            starts_at=starts,
            ends_at=ends,
            venue=venue,
            organizer_name=(organizer.get("name") or "").strip() or None,
            genre=(rec.get("format_name") or rec.get("theme_name") or "").strip() or None,
            ticket_url=rec.get("url"),
            source_url=rec.get("url"),
            # sort_keys: hash estavel entre execucoes (idempotencia da evidencia)
            raw_payload=json.dumps(rec, ensure_ascii=False, sort_keys=True),
        ))
    return out


class SymplaSource:
    """Fonte real #2: eventos de festas/shows de SP via API de busca da Sympla."""

    def __init__(self, *, endpoint: str = SYMPLA_SEARCH_ENDPOINT,
                 page_size: int = 100, max_pages: int = 20,
                 reference: date | None = None, timeout: float = 30.0) -> None:
        self._endpoint = endpoint
        self._page_size = page_size
        self._max_pages = max_pages
        self._reference = reference
        self._timeout = timeout

    def venues(self) -> list[RawVenue]:
        return []  # venues vem EMBUTIDOS nos eventos

    def event_pages(self) -> list[RawEventPage]:
        return []

    def events(self) -> list[RawEvent]:
        reference = self._reference or date.today()
        out: list[RawEvent] = []
        for page in range(1, self._max_pages + 1):
            resp = httpx.post(
                self._endpoint,
                json={"service": "/v4/search",
                      "params": {"cityIn": [_CITY], "limit": self._page_size, "page": page}},
                headers={"User-Agent": _USER_AGENT, "Content-Type": "application/json"},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("data") or []
            out.extend(parse_search_records(data, reference=reference))
            if len(batch) < self._page_size:
                break
        return out
```

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_sympla_source.py -q`
Expected: PASS (2 testes). Suíte inteira: **86**.

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/sympla_source.py tests/test_sympla_source.py && git commit -m "feat(ingestion): fonte Sympla (API de busca, festas/shows de SP)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 5: Runner `ingest_sympla` + README + smoke REAL 2x

**Files:**
- Create: `src/nightlife/ingest_sympla.py`
- Modify: `README.md`

- [ ] **Step 1: Criar o runner** — create `src/nightlife/ingest_sympla.py`:

```python
# src/nightlife/ingest_sympla.py
"""Ingere eventos reais de festas/shows de SP da Sympla no banco.

Uso: .venv/Scripts/python -m nightlife.ingest_sympla
Re-executar e seguro: evidencia idempotente + dedupe por ticket_url.
"""
from __future__ import annotations

import truststore

# Cert store do Windows (antivirus intercepta TLS re-assinando com CA propria).
truststore.inject_into_ssl()

from datetime import date

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.pipeline import run_ingestion
from .ingestion.sympla_source import SymplaSource
from .models import Event, Organizer, Venue


def main() -> None:
    source = SymplaSource()
    with SessionLocal() as session:
        run = run_ingestion(session, source, reference=date.today(), label="sympla")
        session.commit()
        venues = session.scalar(select(func.count()).select_from(Venue))
        events = session.scalar(select(func.count()).select_from(Event))
        organizers = session.scalar(select(func.count()).select_from(Organizer))
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"DB agora: {venues} venues | {events} events | {organizers} organizers")
        if run.errors:
            print("erros:\n" + run.errors[:2000])


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: README** — na seção "### Ingestão real: OpenStreetMap", adicione ao bloco bash a linha:

```bash
.venv/Scripts/python -m nightlife.ingest_sympla   # eventos de festas/shows de SP (Sympla)
```

- [ ] **Step 3: Suíte inteira**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest -q -o console_output_style=count -p no:warnings`
Expected: **86 passed** (`[86/86]`).

- [ ] **Step 4: Smoke REAL 2x** (rede real; timeout generoso)

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m alembic upgrade head && .venv/Scripts/python -m nightlife.ingest_sympla`
Expected: `status=finished`, `found` na casa de dezenas-a-centenas, e as contagens de venues/events/organizers crescendo.

**Calibração permitida NESTE step (e só neste):** se `found=0`, imprima uma amostra da resposta real da API (one-liner httpx com truststore) e ajuste APENAS as constantes `_PARTY_THEME`/`_PARTY_COLLECTION`/params do POST em `sympla_source.py` para o que a API realmente devolve (e atualize a fixture do teste se o nome do campo divergir). NÃO altere a lógica.

Depois rode UMA SEGUNDA VEZ e compare: as contagens NÃO podem inflar significativamente (evidência idempotente + dedupe por ticket_url; eventos novos legítimos podem aparecer). Reporte os dois pares de números.

Se a API falhar (4xx/5xx), reporte a saída (DONE_WITH_CONCERNS) — não fique em loop.

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingest_sympla.py README.md src/nightlife/ingestion/sympla_source.py tests/test_sympla_source.py && git commit -m "feat(ingestion): runner ingest_sympla + README (+calibracao de filtros se houve)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Coverage map (Plano F ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §3 `RawEvent` + `Source.events()` (Mock/OSM com `[]`) | Task 0 |
| §6 dia = America/Sao_Paulo (+ teste do caso limite) | Task 1 |
| §5 organizer de primeira classe (helper + `organizer_id` + gap-fill) | Task 2 |
| §4 terceiro loop do pipeline (venue embutido + organizer + evento; falha de fetch coberta pelo try existente) | Task 3 |
| §7 `parse_search_records` puro + `SymplaSource` paginada + filtro client-side | Task 4 |
| §8–9 runner + smoke real 2x + calibração de constantes | Task 5 |

**Fora deste plano:** Shotgun (429), digest Telegram, revisão dos dedupe_candidates — próximos do roadmap.
