# Nightlife App — Plano B: Persistência & Repositórios — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir a camada de persistência do nightlife-app — Postgres/PostGIS (via Docker), os modelos SQLAlchemy de todas as tabelas com evidência, e os repositórios que gravam venues/events reusando o núcleo de domínio do Plano A (matching → scoring → dedupe).

**Architecture:** SQLAlchemy 2.0 declarativo (síncrono) sobre Postgres. `db.py` expõe `Base`/engine/sessão; `models.py` define as tabelas; `persistence/` tem os repositórios (`upsert_venue`, `upsert_event`) que orquestram domínio + evidência. Testes rodam contra um Postgres de teste real (Docker), cada teste numa transação revertida. Geo no esqueleto é `lat`/`lng` (Float); PostGIS fica habilitado para evolução futura.

**Tech Stack:** Python 3.14 · SQLAlchemy 2.0 · psycopg 3 (`psycopg[binary]`) · Postgres 16 + PostGIS (Docker `postgis/postgis:16-3.4`) · pytest. Reusa `nightlife.domain.*` do Plano A.

**Convenções:**
- Rode tudo pelo venv: `.venv/Scripts/python -m ...` (Windows). cwd do shell RESETA entre chamadas Bash — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Todo commit termina com: `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`
- **Pré-requisito dos testes:** o Postgres precisa estar de pé — `docker compose up -d --wait` (Task 0 cria o `docker-compose.yml`). Os testes de domínio do Plano A (35) continuam rodando sem DB.

---

## File Structure

```
nightlife-app/
  docker-compose.yml                  # Postgres+PostGIS (Task 0)
  .env.example                        # DATABASE_URL / TEST_DATABASE_URL (Task 0)
  src/nightlife/
    config.py                         # le as URLs do ambiente (Task 0)
    db.py                             # Base, engine, SessionLocal (Task 1)
    models.py                         # todas as tabelas SQLAlchemy (Task 1)
    persistence/
      __init__.py
      inputs.py                       # VenueInput, EventInput, SourceInfo (Task 2)
      venues_repo.py                  # upsert_venue (Task 2)
      events_repo.py                  # upsert_event (Task 3)
  tests/
    conftest.py                       # cria DB de teste + sessao transacional (Task 0)
    test_models.py                    # smoke do schema (Task 1)
    test_venues_repo.py               # (Task 2)
    test_events_repo.py               # (Task 3)
```

Responsabilidades: `db.py` = wiring de conexão; `models.py` = schema; `persistence/*` = regras de escrita (reusa `domain/`). `inputs.py` desacopla o contrato dos repositórios da forma como o pipeline (Plano C) monta os dados.

---

## Task 0: Setup de persistência (Docker, deps, config, conftest)

**Files:**
- Modify: `pyproject.toml`
- Create: `docker-compose.yml`, `.env.example`, `src/nightlife/config.py`, `tests/conftest.py`

- [ ] **Step 1: Adicionar dependências no `pyproject.toml`**

Substitua o bloco `dependencies = [...]` por:

```toml
dependencies = [
    "beautifulsoup4>=4.12",
    "tzdata>=2024.1",
    "sqlalchemy>=2.0",
    "psycopg[binary]>=3.1",
]
```

- [ ] **Step 2: Instalar as novas deps**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pip install -e ".[dev]"`
Expected: instala `sqlalchemy` e `psycopg` sem erro.

- [ ] **Step 3: Criar `docker-compose.yml`**

```yaml
services:
  db:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_USER: nightlife
      POSTGRES_PASSWORD: nightlife
      POSTGRES_DB: nightlife
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U nightlife"]
      interval: 3s
      timeout: 3s
      retries: 15
```

- [ ] **Step 4: Criar `.env.example`**

```dotenv
DATABASE_URL=postgresql+psycopg://nightlife:nightlife@localhost:5432/nightlife
TEST_DATABASE_URL=postgresql+psycopg://nightlife:nightlife@localhost:5432/nightlife_test
```

- [ ] **Step 5: Criar `src/nightlife/config.py`**

```python
# src/nightlife/config.py
from __future__ import annotations

import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://nightlife:nightlife@localhost:5432/nightlife",
)
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://nightlife:nightlife@localhost:5432/nightlife_test",
)
```

- [ ] **Step 6: Subir o Postgres**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait`
Expected: container `db` sobe e fica `healthy`.

- [ ] **Step 7: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add pyproject.toml docker-compose.yml .env.example src/nightlife/config.py && git commit -m "chore(persistence): docker postgres, deps e config

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

> Nota: a suíte de domínio do Plano A continua passando (35): `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest -q`. O `conftest.py` e os testes de DB chegam na Task 1, depois que `nightlife.db`/`nightlife.models` existirem.

---

## Task 1: `db.py` + modelos SQLAlchemy

**Files:**
- Create: `src/nightlife/db.py`, `src/nightlife/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_models.py
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nightlife.models import Venue, VenueSource, Event, EventSource, IngestionRun

SP = ZoneInfo("America/Sao_Paulo")


def test_create_and_read_venue_with_source(session):
    v = Venue(name="Lab Club", category="nightclub", lat=-23.561, lng=-46.656,
              status="operational", confidence=70, is_monitored=True)
    session.add(v)
    session.flush()
    session.add(VenueSource(
        venue_id=v.id, source_type="google_places", source_url="http://x",
        raw_payload_hash="abc", extracted_fields={"name": "Lab Club"},
        confidence_contribution=30,
    ))
    session.flush()

    got = session.scalars(select(Venue).where(Venue.name == "Lab Club")).one()
    assert got.confidence == 70
    assert got.is_monitored is True
    assert len(got.sources) == 1
    assert got.sources[0].extracted_fields["name"] == "Lab Club"


def test_create_event_with_venue_and_source(session):
    v = Venue(name="Audio", lat=-23.5, lng=-46.6)
    session.add(v)
    session.flush()
    e = Event(name="Mamba Negra", starts_at=datetime(2026, 6, 13, 23, 0, tzinfo=SP),
              venue_id=v.id, status="scheduled", confidence=85,
              lineup_text="DJ A, DJ B", ticket_url="http://t")
    session.add(e)
    session.flush()
    session.add(EventSource(
        event_id=e.id, source_type="ticketing", source_url="http://t",
        raw_payload_hash="z", extracted_fields={}, confidence_contribution=25,
    ))
    session.flush()
    assert e.venue.name == "Audio"
    assert len(e.sources) == 1


def test_ingestion_run_row(session):
    run = IngestionRun(source="mock", status="finished",
                       records_found=3, records_created=2, records_updated=1)
    session.add(run)
    session.flush()
    assert run.id is not None
    assert run.records_found == 3
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.models'` (ou `nightlife.db`).

- [ ] **Step 3: Criar `src/nightlife/db.py`**

```python
# src/nightlife/db.py
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
```

- [ ] **Step 4: Criar `src/nightlife/models.py`**

```python
# src/nightlife/models.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Venue(Base):
    __tablename__ = "venues"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(50), default=None)
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lng: Mapped[float | None] = mapped_column(Float, default=None)
    address: Mapped[str | None] = mapped_column(String(500), default=None)
    status: Mapped[str] = mapped_column(String(30), default="unverified")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    is_monitored: Mapped[bool] = mapped_column(default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sources: Mapped[list["VenueSource"]] = relationship(
        back_populates="venue", cascade="all, delete-orphan"
    )
    events: Mapped[list["Event"]] = relationship(back_populates="venue")


class VenueSource(Base):
    __tablename__ = "venue_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_payload_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    extracted_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_contribution: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    venue: Mapped["Venue"] = relationship(back_populates="sources")


class Organizer(Base):
    __tablename__ = "organizers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    instagram: Mapped[str | None] = mapped_column(String(200), default=None)
    website: Mapped[str | None] = mapped_column(String(500), default=None)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(400))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), default=None)
    organizer_id: Mapped[int | None] = mapped_column(ForeignKey("organizers.id"), default=None)
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    lineup_text: Mapped[str | None] = mapped_column(Text, default=None)
    genre: Mapped[str | None] = mapped_column(String(80), default=None)
    ticket_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    raw_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    venue: Mapped["Venue | None"] = relationship(back_populates="events")
    sources: Mapped[list["EventSource"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventSource(Base):
    __tablename__ = "event_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_payload_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    extracted_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_contribution: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event: Mapped["Event"] = relationship(back_populates="sources")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(60))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    status: Mapped[str] = mapped_column(String(30), default="running")
    records_found: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[str | None] = mapped_column(Text, default=None)


class DedupeCandidate(Base):
    __tablename__ = "dedupe_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # "event" | "venue"
    a_id: Mapped[int] = mapped_column(Integer)
    b_id: Mapped[int] = mapped_column(Integer)
    similarity_score: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(20))  # "auto_merge" | "review" | "distinct"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VerificationLog(Base):
    __tablename__ = "verification_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20))  # "venue" | "event"
    entity_id: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 5: Criar `tests/conftest.py`** (cria o DB de teste e dá uma sessão transacional por teste)

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nightlife.config import TEST_DATABASE_URL, DATABASE_URL
from nightlife import db as db_module
from nightlife.db import Base
import nightlife.models  # noqa: F401  (registra os models no metadata)


def _ensure_test_database():
    """Cria o database de teste se nao existir (CREATE DATABASE exige autocommit)."""
    admin = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = 'nightlife_test'")
            ).scalar()
            if not exists:
                conn.execute(text("CREATE DATABASE nightlife_test"))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def engine():
    _ensure_test_database()
    eng = create_engine(TEST_DATABASE_URL, future=True)
    db_module.engine = eng
    db_module.SessionLocal.configure(bind=eng)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    """Sessao isolada por teste: tudo e revertido no fim (nada persiste)."""
    conn = engine.connect()
    trans = conn.begin()
    sess = Session(bind=conn, join_transaction_mode="create_savepoint", future=True)
    try:
        yield sess
    finally:
        sess.close()
        trans.rollback()
        conn.close()
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_models.py -q`
Expected: PASS (3 testes). A suíte inteira deve dar **38 passed**.

- [ ] **Step 7: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/db.py src/nightlife/models.py tests/conftest.py tests/test_models.py && git commit -m "feat(persistence): db wiring + modelos SQLAlchemy + conftest de DB

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: Repositório de venues (`upsert_venue`)

**Files:**
- Create: `src/nightlife/persistence/__init__.py`, `src/nightlife/persistence/inputs.py`, `src/nightlife/persistence/venues_repo.py`
- Test: `tests/test_venues_repo.py`

Reusa `match_venue`/`VenueRef` (matching) e `score_venue`/`VenueSignals` (scoring) do Plano A. Faz matching contra os venues existentes: se casa, reusa e adiciona evidência; senão, cria. Sempre grava um `VenueSource`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_venues_repo.py
from sqlalchemy import select

from nightlife.models import Venue, VenueSource
from nightlife.domain.scoring import VenueSignals
from nightlife.persistence.inputs import VenueInput, SourceInfo
from nightlife.persistence.venues_repo import upsert_venue


def _src(stype="google_places"):
    return SourceInfo(source_type=stype, source_url="http://x",
                      raw_payload='{"k":1}', extracted_fields={"k": 1})


def test_creates_new_venue_with_score_and_source(session):
    v = upsert_venue(
        session,
        VenueInput(name="Lab Club", lat=-23.561, lng=-46.656, address="R. X", category="nightclub"),
        SourceInfo(source_type="google_places", source_url="http://g", raw_payload="p", extracted_fields={}),
        VenueSignals(google_places_operational=True, official_website=True),
    )
    session.flush()
    assert v.id is not None
    assert v.confidence == 30 + 20  # places + site
    rows = session.scalars(select(Venue)).all()
    assert len(rows) == 1
    srcs = session.scalars(select(VenueSource)).all()
    assert len(srcs) == 1 and srcs[0].confidence_contribution == v.confidence


def test_matching_reuses_existing_venue(session):
    upsert_venue(session, VenueInput(name="Lab Club", lat=-23.561, lng=-46.656),
                 _src(), VenueSignals(google_places_operational=True))
    session.flush()
    v2 = upsert_venue(session, VenueInput(name="lab club", lat=-23.5611, lng=-46.6561),
                      _src("osm"), VenueSignals(osm_match=True))
    session.flush()
    assert len(session.scalars(select(Venue)).all()) == 1      # nao duplicou
    assert len(session.scalars(select(VenueSource)).all()) == 2  # duas evidencias


def test_distinct_names_create_two_venues(session):
    upsert_venue(session, VenueInput(name="Lab Club"), _src(), VenueSignals())
    upsert_venue(session, VenueInput(name="Trackers"), _src(), VenueSignals())
    session.flush()
    assert len(session.scalars(select(Venue)).all()) == 2
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_venues_repo.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.persistence.venues_repo'`.

- [ ] **Step 3: Implementar `inputs.py` e `venues_repo.py`**

Create `src/nightlife/persistence/__init__.py` (empty), then `src/nightlife/persistence/inputs.py`:

```python
# src/nightlife/persistence/inputs.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SourceInfo:
    source_type: str
    source_url: str | None = None
    raw_payload: str = ""
    extracted_fields: dict = field(default_factory=dict)


@dataclass
class VenueInput:
    name: str
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    category: str | None = None


@dataclass
class EventInput:
    name: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    venue_id: int | None = None
    venue_name: str | None = None
    organizer: str | None = None
    lineup_text: str | None = None
    genre: str | None = None
    ticket_url: str | None = None
    raw_fields: dict = field(default_factory=dict)
```

Then `src/nightlife/persistence/venues_repo.py`:

```python
# src/nightlife/persistence/venues_repo.py
from __future__ import annotations

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.matching import VenueRef, match_venue
from ..domain.scoring import VenueSignals, score_venue
from ..models import Venue, VenueSource
from .inputs import SourceInfo, VenueInput


def _hash(payload: str) -> str:
    return hashlib.sha256((payload or "").encode("utf-8")).hexdigest()


def upsert_venue(
    session: Session, candidate: VenueInput, source: SourceInfo, signals: VenueSignals
) -> Venue:
    existing = session.scalars(select(Venue)).all()
    refs = [VenueRef(v.id, v.name, v.address, v.lat, v.lng) for v in existing]
    match = match_venue(
        VenueRef(None, candidate.name, candidate.address, candidate.lat, candidate.lng), refs
    )

    if match is not None:
        venue = session.get(Venue, match.venue.id)
        venue.last_seen_at = func.now()
        # preenche lacunas sem sobrescrever dados ja existentes
        venue.lat = venue.lat if venue.lat is not None else candidate.lat
        venue.lng = venue.lng if venue.lng is not None else candidate.lng
        venue.address = venue.address or candidate.address
        venue.category = venue.category or candidate.category
    else:
        venue = Venue(
            name=candidate.name, lat=candidate.lat, lng=candidate.lng,
            address=candidate.address, category=candidate.category, status="unverified",
        )
        session.add(venue)
        session.flush()

    venue.confidence = score_venue(signals)
    session.add(VenueSource(
        venue_id=venue.id,
        source_type=source.source_type,
        source_url=source.source_url,
        raw_payload_hash=_hash(source.raw_payload),
        extracted_fields=source.extracted_fields,
        confidence_contribution=venue.confidence,
    ))
    return venue
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_venues_repo.py -q`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/persistence/ tests/test_venues_repo.py && git commit -m "feat(persistence): upsert_venue com matching, scoring e evidencia

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: Repositório de events (`upsert_event`)

**Files:**
- Create: `src/nightlife/persistence/events_repo.py`
- Test: `tests/test_events_repo.py`

Reusa `EventKey`/`compare` (dedupe) e `score_event`/`EventSignals` (scoring) do Plano A. Compara o candidato com os eventos existentes: `auto_merge` → reusa e adiciona evidência; `review` → cria novo **e** registra um `DedupeCandidate`; `distinct` → cria novo. Sempre grava `EventSource`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_events_repo.py
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nightlife.models import Venue, Event, EventSource, DedupeCandidate
from nightlife.domain.scoring import EventSignals
from nightlife.persistence.inputs import EventInput, SourceInfo
from nightlife.persistence.events_repo import upsert_event

SP = ZoneInfo("America/Sao_Paulo")


def _venue(session, name="Lab Club"):
    v = Venue(name=name)
    session.add(v)
    session.flush()
    return v


def _src(stype="ticketing"):
    return SourceInfo(source_type=stype, source_url="http://t", raw_payload="p", extracted_fields={})


def _evin(name, dt, venue, ticket=None):
    # liga o evento a um venue real: o dedupe usa o nome do venue na comparacao
    return EventInput(name=name, starts_at=dt, venue_id=venue.id, venue_name=venue.name, ticket_url=ticket)


def test_creates_event_with_score_and_source(session):
    v = _venue(session)
    e = upsert_event(
        session,
        _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v),
        _src(),
        EventSignals(future_date=True, venue_matched=True, ticketing_source=True),
    )
    session.flush()
    assert e.id is not None
    assert e.confidence == 20 + 20 + 25
    assert len(session.scalars(select(EventSource)).all()) == 1


def test_duplicate_event_auto_merges(session):
    v = _venue(session)
    upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v),
                 _src(), EventSignals(future_date=True))
    session.flush()
    upsert_event(session, _evin("MAMBA NEGRA", datetime(2026, 6, 13, 23, 30, tzinfo=SP), v),
                 _src("instagram"), EventSignals(future_date=True))
    session.flush()
    assert len(session.scalars(select(Event)).all()) == 1       # merge
    assert len(session.scalars(select(EventSource)).all()) == 2  # duas evidencias


def test_distinct_events_create_two(session):
    v1 = _venue(session, "Lab Club")
    v2 = _venue(session, "Cargo")
    upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v1),
                 _src(), EventSignals(future_date=True))
    upsert_event(session, _evin("Gop Tun", datetime(2026, 7, 20, 16, 0, tzinfo=SP), v2),
                 _src(), EventSignals(future_date=True))
    session.flush()
    assert len(session.scalars(select(Event)).all()) == 2


def test_medium_confidence_creates_dedupe_candidate(session):
    v = _venue(session)
    # mesmo nome e venue, ~16h de diferenca => "review" (score ~0.82: nao auto-merge, nao distinct)
    upsert_event(session, _evin("Festa X", datetime(2026, 6, 13, 22, 0, tzinfo=SP), v),
                 _src(), EventSignals(future_date=True))
    session.flush()
    upsert_event(session, _evin("Festa X", datetime(2026, 6, 14, 14, 0, tzinfo=SP), v),
                 _src("instagram"), EventSignals(future_date=True))
    session.flush()
    assert len(session.scalars(select(Event)).all()) == 2          # criou novo
    cands = session.scalars(select(DedupeCandidate)).all()
    assert len(cands) == 1 and cands[0].decision == "review"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_events_repo.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.persistence.events_repo'`.

- [ ] **Step 3: Implementar `events_repo.py`**

```python
# src/nightlife/persistence/events_repo.py
from __future__ import annotations

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.dedupe import EventKey, compare
from ..domain.scoring import EventSignals, score_event
from ..models import DedupeCandidate, Event, EventSource
from .inputs import EventInput, SourceInfo


def _hash(payload: str) -> str:
    return hashlib.sha256((payload or "").encode("utf-8")).hexdigest()


def _key_from_input(c: EventInput) -> EventKey:
    return EventKey(name=c.name, starts_at=c.starts_at, venue_name=c.venue_name,
                    organizer=c.organizer, ticket_url=c.ticket_url)


def _key_from_row(e: Event) -> EventKey:
    venue_name = e.venue.name if e.venue is not None else None
    return EventKey(name=e.name, starts_at=e.starts_at, venue_name=venue_name,
                    organizer=None, ticket_url=e.ticket_url)


def upsert_event(
    session: Session, candidate: EventInput, source: SourceInfo, signals: EventSignals
) -> Event:
    cand_key = _key_from_input(candidate)
    existing = session.scalars(select(Event)).all()

    best_row = None
    best = None
    for row in existing:
        result = compare(cand_key, _key_from_row(row))
        if best is None or result.score > best.score:
            best, best_row = result, row

    if best is not None and best.decision == "auto_merge":
        event = best_row
        event.last_seen_at = func.now()
    else:
        event = Event(
            name=candidate.name, starts_at=candidate.starts_at, ends_at=candidate.ends_at,
            venue_id=candidate.venue_id, lineup_text=candidate.lineup_text,
            genre=candidate.genre, ticket_url=candidate.ticket_url,
            raw_fields=candidate.raw_fields, status="scheduled",
        )
        session.add(event)
        session.flush()
        if best is not None and best.decision == "review":
            session.add(DedupeCandidate(
                kind="event", a_id=event.id, b_id=best_row.id,
                similarity_score=best.score, decision="review",
            ))

    event.confidence = score_event(signals)
    session.add(EventSource(
        event_id=event.id,
        source_type=source.source_type,
        source_url=source.source_url,
        raw_payload_hash=_hash(source.raw_payload),
        extracted_fields=source.extracted_fields,
        confidence_contribution=event.confidence,
    ))
    return event
```

- [ ] **Step 4: Rodar e ver passar (suíte inteira)**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest -q`
Expected: PASS — domínio (35) + persistência (3 models + 3 venues + 4 events) = **45 passed**.

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/persistence/events_repo.py tests/test_events_repo.py && git commit -m "feat(persistence): upsert_event com dedupe, dedupe_candidates e scoring

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Coverage map (Plano B ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §6.1 tabelas (venues, *_sources, events, organizers, ingestion_runs, dedupe_candidates, verification_logs) | Task 1 |
| §6.2 evidência (source_url, source_type, fetched_at, raw_payload_hash, extracted_fields, confidence_contribution, last_seen_at) | Tasks 1–3 |
| §2 PostgreSQL + PostGIS-ready (lat/lng) | Tasks 0–1 |
| §7 scoring aplicado na escrita | Tasks 2–3 (reusa domínio) |
| §9 dedupe na escrita + dedupe_candidates p/ revisão | Task 3 |
| §4.1 matching reusa venue existente | Task 2 |

**Fora do Plano B (vão pro Plano C):** fonte mock + fixtures, pipeline de ingestão ponta-a-ponta, `ingestion_runs` preenchido pelo pipeline, API FastAPI, migrations Alembic (no esqueleto usamos `create_all`), README. "Futuros" do spec (vision real, Playwright/IG, ticketing/Places/OSM reais, Telegram, telas, decay temporal) seguem adiante.
