# Nightlife App — Plano C: Ingestão (pipeline mock end-to-end) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ligar todas as camadas num pipeline de ingestão end-to-end com dados mock — uma fonte (fixtures de venues + páginas de evento) que passa por extração → matching → scoring → dedupe → persistência, gravando um `IngestionRun`, e um `seed` executável que popula o banco real.

**Architecture:** `ingestion/base.py` define os registros brutos (`RawVenue`, `RawEventPage`) e o `Source` protocol; `signals.py` deriva os sinais de scoring do tipo de fonte; `mock_source.py` lê fixtures JSON; `pipeline.py` orquestra tudo reusando extração (Plano A) e repositórios (Plano B). Testes de integração rodam contra o Postgres de teste (conftest existente).

**Tech Stack:** Python 3.14 · SQLAlchemy 2.0 · pytest. Reusa `nightlife.domain.*`, `nightlife.extraction.*`, `nightlife.persistence.*`. Sem dependências novas.

**Convenções:**
- `.venv/Scripts/python -m ...` (Windows). cwd do shell RESETA entre chamadas Bash — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Postgres já configurado (Docker na porta 5434). Se o container não estiver up: `docker compose up -d --wait`. **Não** mexa em `config.py`/`docker-compose.yml`/`conftest.py`.
- Todo commit termina com: `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`
- Estado atual da suíte: **46 passed**.

---

## File Structure

```
nightlife-app/
  src/nightlife/
    ingestion/
      __init__.py
      base.py             # RawVenue, RawEventPage, Source protocol  (Task 1)
      signals.py          # derive_venue_signals / derive_event_signals  (Task 1)
      mock_source.py      # MockSource (le fixtures)  (Task 2)
      pipeline.py         # run_ingestion  (Task 3)
    fixtures/
      venues.json         # (Task 2)
      event_pages.json    # (Task 2)
    seed.py               # script: roda o pipeline contra o banco real  (Task 4)
  tests/
    test_ingestion_signals.py   # (Task 1)
    test_mock_source.py         # (Task 2)
    test_pipeline.py            # integracao DB  (Task 3)
```

---

## Task 1: Tipos de ingestão + derivação de sinais

**Files:**
- Create: `src/nightlife/ingestion/__init__.py` (empty), `src/nightlife/ingestion/base.py`, `src/nightlife/ingestion/signals.py`
- Test: `tests/test_ingestion_signals.py`

- [ ] **Step 1: Escrever o teste que falha** — create `tests/test_ingestion_signals.py`:

```python
# tests/test_ingestion_signals.py
from nightlife.ingestion.signals import derive_venue_signals, derive_event_signals


def test_venue_signals_from_source_type():
    assert derive_venue_signals("google_places").google_places_operational is True
    assert derive_venue_signals("osm").osm_match is True
    assert derive_venue_signals("official_website").official_website is True
    assert derive_venue_signals("instagram").instagram_link is True
    # tipo desconhecido nao liga nenhum sinal
    s = derive_venue_signals("whatever")
    assert not any([s.google_places_operational, s.osm_match, s.official_website, s.instagram_link])


def test_event_signals_mapping():
    s = derive_event_signals(source_type="ticketing", has_future_date=True, venue_matched=True)
    assert s.future_date is True
    assert s.ticketing_source is True
    assert s.venue_matched is True
    assert s.no_venue is False

    s2 = derive_event_signals(source_type="official_website", has_future_date=False, venue_matched=False)
    assert s2.official_source is True
    assert s2.no_venue is True
    assert s2.ticketing_source is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ingestion_signals.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.ingestion.signals'`.

- [ ] **Step 3: Criar `base.py` e `signals.py`**

Create `src/nightlife/ingestion/__init__.py` (empty), then `src/nightlife/ingestion/base.py`:

```python
# src/nightlife/ingestion/base.py
from __future__ import annotations

from dataclasses import dataclass
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


class Source(Protocol):
    def venues(self) -> Iterable[RawVenue]: ...
    def event_pages(self) -> Iterable[RawEventPage]: ...
```

Then `src/nightlife/ingestion/signals.py`:

```python
# src/nightlife/ingestion/signals.py
from __future__ import annotations

from ..domain.scoring import EventSignals, VenueSignals


def derive_venue_signals(source_type: str) -> VenueSignals:
    return VenueSignals(
        google_places_operational=source_type == "google_places",
        osm_match=source_type == "osm",
        official_website=source_type == "official_website",
        instagram_link=source_type == "instagram",
    )


def derive_event_signals(*, source_type: str, has_future_date: bool, venue_matched: bool) -> EventSignals:
    return EventSignals(
        future_date=has_future_date,
        venue_matched=venue_matched,
        official_source=source_type in ("official_website", "organizer"),
        ticketing_source=source_type == "ticketing",
        no_venue=not venue_matched,
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ingestion_signals.py -q`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/ tests/test_ingestion_signals.py && git commit -m "feat(ingestion): tipos de fonte + derivacao de sinais de scoring

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: Fonte mock + fixtures

**Files:**
- Create: `src/nightlife/fixtures/venues.json`, `src/nightlife/fixtures/event_pages.json`, `src/nightlife/ingestion/mock_source.py`
- Test: `tests/test_mock_source.py`

- [ ] **Step 1: Escrever o teste que falha** — create `tests/test_mock_source.py`:

```python
# tests/test_mock_source.py
from pathlib import Path

from nightlife.ingestion.base import RawVenue, RawEventPage
from nightlife.ingestion.mock_source import MockSource

FIXTURES = Path("src/nightlife/fixtures")


def test_loads_fixtures():
    src = MockSource.from_fixtures(FIXTURES / "venues.json", FIXTURES / "event_pages.json")
    venues = list(src.venues())
    pages = list(src.event_pages())
    assert len(venues) >= 3 and all(isinstance(v, RawVenue) for v in venues)
    assert len(pages) >= 3 and all(isinstance(p, RawEventPage) for p in pages)
    # ha pelo menos uma pagina de cada tipo coberto
    kinds = {p.kind for p in pages}
    assert {"jsonld", "html", "freetext"} <= kinds


def test_in_memory_construction():
    src = MockSource([RawVenue(name="X", source_type="osm")], [])
    assert list(src.venues())[0].name == "X"
    assert list(src.event_pages()) == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_mock_source.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.ingestion.mock_source'`.

- [ ] **Step 3: Criar as fixtures e `mock_source.py`**

Create `src/nightlife/fixtures/venues.json`:

```json
[
  {"name": "Lab Club", "source_type": "google_places", "lat": -23.5613, "lng": -46.6565, "address": "R. Augusta, 1000", "category": "nightclub", "source_url": "https://maps.google.com/lab", "raw_payload": "{\"place_id\":\"lab1\"}"},
  {"name": "Audio SP", "source_type": "osm", "lat": -23.5290, "lng": -46.6720, "address": "Av. Francisco Matarazzo, 694", "category": "live_music_venue", "source_url": "https://osm.org/audio", "raw_payload": "{\"osm_id\":42}"},
  {"name": "Trackers", "source_type": "official_website", "lat": -23.5450, "lng": -46.6420, "address": "R. Augusta, 501", "category": "nightclub", "source_url": "https://trackers.com.br", "raw_payload": "{\"site\":true}"}
]
```

Create `src/nightlife/fixtures/event_pages.json`:

```json
[
  {"kind": "jsonld", "source_type": "ticketing", "source_url": "https://sympla.com.br/mamba", "content": "<html><head><script type=\"application/ld+json\">{\"@context\":\"https://schema.org\",\"@type\":\"Event\",\"name\":\"Mamba Negra\",\"startDate\":\"2099-06-13T23:00:00-03:00\",\"location\":{\"@type\":\"Place\",\"name\":\"Lab Club\"},\"offers\":{\"@type\":\"Offer\",\"url\":\"https://sympla.com.br/mamba\"}}</script></head><body></body></html>"},
  {"kind": "html", "source_type": "event_page", "source_url": "https://audio.com/agenda", "content": "<div itemscope itemtype=\"https://schema.org/Event\"><span itemprop=\"name\">Carlos Capslock</span><meta itemprop=\"startDate\" content=\"2099-07-20T22:00:00-03:00\"></div>"},
  {"kind": "freetext", "source_type": "instagram", "source_url": "https://instagram.com/p/abc", "content": "GOP TUN\nDOM 20/07 a partir das 16h\nopen air\ningressos: https://shotgun.live/goptun"}
]
```

Then create `src/nightlife/ingestion/mock_source.py`:

```python
# src/nightlife/ingestion/mock_source.py
from __future__ import annotations

import json
from pathlib import Path

from .base import RawEventPage, RawVenue


class MockSource:
    """Fonte de teste que serve registros a partir de listas em memoria ou de fixtures JSON."""

    def __init__(self, venues: list[RawVenue], event_pages: list[RawEventPage]) -> None:
        self._venues = venues
        self._pages = event_pages

    @classmethod
    def from_fixtures(cls, venues_path, event_pages_path) -> "MockSource":
        venues = [RawVenue(**d) for d in json.loads(Path(venues_path).read_text(encoding="utf-8"))]
        pages = [RawEventPage(**d) for d in json.loads(Path(event_pages_path).read_text(encoding="utf-8"))]
        return cls(venues, pages)

    def venues(self) -> list[RawVenue]:
        return list(self._venues)

    def event_pages(self) -> list[RawEventPage]:
        return list(self._pages)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_mock_source.py -q`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/fixtures/ src/nightlife/ingestion/mock_source.py tests/test_mock_source.py && git commit -m "feat(ingestion): fonte mock + fixtures (venues e paginas de evento)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: Pipeline de ingestão (end-to-end)

**Files:**
- Create: `src/nightlife/ingestion/pipeline.py`
- Test: `tests/test_pipeline.py`

Orquestra: para cada `RawVenue` → `upsert_venue` (sinais derivados do tipo de fonte). Para cada `RawEventPage` → extrai (jsonld/html/freetext conforme `kind`), resolve o venue pelo nome extraído (matching contra o banco), deriva sinais e `upsert_event`. Grava um `IngestionRun` com contagens. `has_future_date` é avaliado contra `reference` (determinístico).

- [ ] **Step 1: Escrever o teste que falha** — create `tests/test_pipeline.py`:

```python
# tests/test_pipeline.py
from datetime import date

from sqlalchemy import select

from nightlife.models import Venue, Event, IngestionRun
from nightlife.ingestion.base import RawVenue, RawEventPage
from nightlife.ingestion.mock_source import MockSource
from nightlife.ingestion.pipeline import run_ingestion

REF = date(2026, 6, 1)

JSONLD = (
    '<script type="application/ld+json">'
    '{"@type":"Event","name":"Mamba Negra","startDate":"2099-06-13T23:00:00-03:00",'
    '"location":{"name":"Lab Club"},"offers":{"url":"https://t/x"}}</script>'
)


def test_pipeline_creates_venue_event_and_run(session):
    src = MockSource(
        [RawVenue(name="Lab Club", source_type="google_places", lat=-23.561, lng=-46.656)],
        [RawEventPage(kind="jsonld", content=JSONLD, source_type="ticketing", source_url="https://t/x")],
    )
    run = run_ingestion(session, src, reference=REF)
    session.flush()

    assert run.status == "finished"
    assert run.records_found == 2  # 1 venue + 1 pagina

    venues = session.scalars(select(Venue)).all()
    assert len(venues) == 1 and venues[0].confidence == 30  # google_places

    events = session.scalars(select(Event)).all()
    assert len(events) == 1
    e = events[0]
    assert e.name == "Mamba Negra"
    assert e.venue_id == venues[0].id                      # resolveu "Lab Club"
    assert e.confidence == 20 + 20 + 25                    # future + venue_matched + ticketing

    runs = session.scalars(select(IngestionRun)).all()
    assert len(runs) == 1 and runs[0].finished_at is not None


def test_pipeline_event_without_resolvable_venue(session):
    # freetext nao extrai venue -> evento fica sem venue e marcado no_venue
    flyer = "GOP TUN\n20/07 16h\nhttps://shotgun.live/x"
    src = MockSource([], [RawEventPage(kind="freetext", content=flyer, source_type="instagram")])
    run = run_ingestion(session, src, reference=REF)
    session.flush()
    events = session.scalars(select(Event)).all()
    assert len(events) == 1
    assert events[0].venue_id is None
    assert run.records_created == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.ingestion.pipeline'`.

- [ ] **Step 3: Criar `pipeline.py`**

```python
# src/nightlife/ingestion/pipeline.py
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.matching import VenueRef, match_venue
from ..extraction.freetext import extract_freetext_deterministic
from ..extraction.html_patterns import parse_html_patterns
from ..extraction.jsonld import parse_jsonld_events
from ..models import IngestionRun, Venue
from ..persistence.events_repo import upsert_event
from ..persistence.inputs import EventInput, SourceInfo, VenueInput
from ..persistence.venues_repo import upsert_venue
from .base import RawEventPage, Source
from .signals import derive_event_signals, derive_venue_signals


def _extract_page(page: RawEventPage, reference: date):
    if page.kind == "jsonld":
        return parse_jsonld_events(page.content, source_url=page.source_url)
    if page.kind == "html":
        return parse_html_patterns(page.content, source_url=page.source_url)
    return [extract_freetext_deterministic(page.content, reference=reference, source_url=page.source_url)]


def _resolve_venue(session: Session, venue_name: str | None) -> Venue | None:
    if not venue_name:
        return None
    existing = session.scalars(select(Venue)).all()
    refs = [VenueRef(v.id, v.name, v.address, v.lat, v.lng) for v in existing]
    m = match_venue(VenueRef(None, venue_name), refs)
    return session.get(Venue, m.venue.id) if m is not None else None


def run_ingestion(session: Session, source: Source, *, reference: date, label: str = "mock") -> IngestionRun:
    run = IngestionRun(source=label, status="running")
    session.add(run)
    session.flush()

    found = created = 0
    errors: list[str] = []

    for rv in source.venues():
        found += 1
        try:
            upsert_venue(
                session,
                VenueInput(name=rv.name, lat=rv.lat, lng=rv.lng, address=rv.address, category=rv.category),
                SourceInfo(source_type=rv.source_type, source_url=rv.source_url, raw_payload=rv.raw_payload),
                derive_venue_signals(rv.source_type),
            )
            created += 1
        except Exception as exc:  # noqa: BLE001 — registra e segue
            errors.append(f"venue {rv.name!r}: {exc}")

    for page in source.event_pages():
        found += 1
        try:
            for ev in _extract_page(page, reference):
                if not ev.name:
                    continue
                venue = _resolve_venue(session, ev.venue_name)
                has_future = ev.starts_at is not None and ev.starts_at.date() >= reference
                signals = derive_event_signals(
                    source_type=page.source_type,
                    has_future_date=has_future,
                    venue_matched=venue is not None,
                )
                upsert_event(
                    session,
                    EventInput(
                        name=ev.name, starts_at=ev.starts_at,
                        venue_id=venue.id if venue is not None else None,
                        venue_name=ev.venue_name, ticket_url=ev.ticket_url,
                        raw_fields=ev.raw,
                    ),
                    SourceInfo(source_type=page.source_type, source_url=page.source_url, raw_payload=page.content),
                    signals,
                )
                created += 1
        except Exception as exc:  # noqa: BLE001 — registra e segue
            errors.append(f"page {page.source_url!r}: {exc}")

    run.status = "finished"
    run.records_found = found
    run.records_created = created
    run.finished_at = datetime.now(timezone.utc)
    run.errors = "\n".join(errors) or None
    session.flush()
    return run
```

- [ ] **Step 4: Rodar e ver passar (suíte inteira)**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest -q`
Expected: PASS — 46 (anteriores) + 2 (signals) + 2 (mock_source) + 2 (pipeline) = **52 passed**.

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/pipeline.py tests/test_pipeline.py && git commit -m "feat(ingestion): pipeline end-to-end (fonte -> extracao -> repos -> run)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 4: Script `seed` (rodar o fio inteiro contra o banco real)

**Files:**
- Create: `src/nightlife/seed.py`

Sem teste automatizado (é um entrypoint de I/O contra o banco de dev); a verificação é rodá-lo e inspecionar a saída.

- [ ] **Step 1: Criar `src/nightlife/seed.py`**

```python
# src/nightlife/seed.py
"""Roda o pipeline de ingestao com as fixtures mock contra o banco real.

Uso: .venv/Scripts/python -m nightlife.seed
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.mock_source import MockSource
from .ingestion.pipeline import run_ingestion
from .models import Event, Venue

FIXTURES = Path(__file__).parent / "fixtures"


def main() -> None:
    source = MockSource.from_fixtures(FIXTURES / "venues.json", FIXTURES / "event_pages.json")
    with SessionLocal() as session:
        run = run_ingestion(session, source, reference=date.today())
        session.commit()
        venues = session.scalar(select(func.count()).select_from(Venue))
        events = session.scalar(select(func.count()).select_from(Event))
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"DB agora: {venues} venues, {events} events")
        if run.errors:
            print("erros:\n" + run.errors)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Garantir schema no banco de dev e rodar o seed**

O banco de dev (`nightlife`) precisa das tabelas. Como ainda não há migrations (Plano D), crie o schema via `create_all` uma vez e rode o seed:

```bash
cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -c "from nightlife.db import engine, Base; import nightlife.models; Base.metadata.create_all(engine); print('schema OK')" && .venv/Scripts/python -m nightlife.seed
```
Expected: imprime `schema OK`, depois algo como `IngestionRun #1: status=finished found=6 created=6` e `DB agora: 3 venues, 3 events`. (Rodar de novo NÃO deve duplicar venues — o matching reusa; pode criar novas linhas de evidência e, dependendo das datas, novos eventos.)

- [ ] **Step 3: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/seed.py && git commit -m "feat(ingestion): script seed roda o pipeline mock contra o banco real

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

> Nota: o seed usa o banco `nightlife` (não o de teste). É idempotente quanto a venues (matching reusa). Como as fixtures de evento usam datas em 2099, elas sempre contam como futuras.

---

## Coverage map (Plano C ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §3 interface de ingestão (fonte) + ingestão mock | Tasks 1, 2 |
| §4.1 "sample ingestion using mock data" | Tasks 2, 4 |
| §6 extração ligada à persistência com evidência | Task 3 |
| §7 scoring aplicado na ingestão (sinais derivados da fonte) | Tasks 1, 3 |
| §9 dedupe na ingestão (via `upsert_event`) | Task 3 |
| §9 `ingestion_runs` preenchido (found/created/finished/errors) | Task 3 |
| §11 walking skeleton: fio fino ponta-a-ponta com mock | Tasks 3, 4 |

**Fora do Plano C (vão pro Plano D):** API FastAPI (`/venues`, `/events`, `/{id}`), migrations Alembic, README. "Futuros" do spec (fontes reais, vision multimodal, Playwright/IG, Telegram, telas, decay temporal, métricas) seguem adiante.
