# Nightlife App — Plano D: API & README (+ migrations) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expor o data layer via HTTP com uma API FastAPI somente-leitura (`/venues`, `/events` com filtros + bbox, e os `/{id}`), versionar o schema com Alembic, e documentar tudo num README — fechando o esqueleto consumível ponta-a-ponta.

**Architecture:** `api/deps.py` provê a sessão; `api/schemas.py` define os modelos de resposta Pydantic; `api/main.py` monta o FastAPI com 4 endpoints que consultam os modelos do Plano B. Testes via `TestClient` com a sessão de teste injetada por dependency override. Alembic versiona o schema (substituindo o `create_all` ad-hoc do `seed`).

**Tech Stack:** Python 3.14 · FastAPI · Uvicorn · Pydantic v2 · httpx (TestClient) · Alembic · SQLAlchemy 2.0 · pytest.

**Convenções:**
- `.venv/Scripts/python -m ...` (Windows). cwd RESETA entre chamadas Bash — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Postgres na porta **5434** (Docker). Se o engine estiver parado: abra o Docker Desktop e aguarde ~1-2 min; depois `docker compose up -d --wait`. **Não** mexa em `config.py`/`docker-compose.yml`/`conftest.py`.
- Testes contra o Postgres de teste (precisa do Docker up). Confirme contagem com `-o console_output_style=count` (no Git Bash, pipe pra grep/tail engole o resumo do pytest).
- Estado atual: **53 testes**. Commits terminam com o trailer `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`.

---

## File Structure

```
nightlife-app/
  src/nightlife/api/
    __init__.py
    deps.py          # get_session (dependency)  (Task 1)
    schemas.py       # VenueOut, EventOut (Pydantic)  (Task 1)
    main.py          # FastAPI app + 4 endpoints  (Task 1)
  alembic.ini        # (Task 3)
  migrations/        # env.py + versions/<rev>_initial.py  (Task 3)
  README.md          # (Task 4)
  tests/test_api.py  # (Task 1)
```

---

## Task 0: Dependências web

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Adicionar deps** — substitua o bloco `dependencies = [...]` por:

```toml
dependencies = [
    "beautifulsoup4>=4.12",
    "tzdata>=2024.1",
    "sqlalchemy>=2.0",
    "psycopg[binary]>=3.1",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "alembic>=1.13",
]
```

E no bloco `[project.optional-dependencies]`, troque a linha `dev` por:

```toml
dev = ["pytest>=8.0", "httpx>=0.27"]
```

- [ ] **Step 2: Instalar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pip install -e ".[dev]"`
Expected: instala fastapi, uvicorn, alembic, httpx sem erro.

- [ ] **Step 3: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add pyproject.toml && git commit -m "chore(api): deps web (fastapi, uvicorn, alembic, httpx)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 1: API FastAPI (`/venues`, `/events`, `/{id}`)

**Files:**
- Create: `src/nightlife/api/__init__.py` (empty), `src/nightlife/api/deps.py`, `src/nightlife/api/schemas.py`, `src/nightlife/api/main.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Escrever o teste que falha** — create `tests/test_api.py`:

```python
# tests/test_api.py
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from nightlife.api.deps import get_session
from nightlife.api.main import app
from nightlife.models import Event, Venue

SP = ZoneInfo("America/Sao_Paulo")


def _client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def test_list_and_get_venue(session):
    v = Venue(name="Lab Club", category="nightclub", lat=-23.561, lng=-46.656,
              status="operational", confidence=70, is_monitored=True)
    session.add(v)
    session.flush()
    client = _client(session)
    try:
        r = client.get("/venues", params={"min_confidence": 50})
        assert r.status_code == 200
        assert any(x["name"] == "Lab Club" for x in r.json())

        # min_confidence alto exclui
        r2 = client.get("/venues", params={"min_confidence": 90})
        assert all(x["name"] != "Lab Club" for x in r2.json())

        # filtro por type
        r3 = client.get("/venues", params={"type": "bar"})
        assert all(x["name"] != "Lab Club" for x in r3.json())

        rid = client.get(f"/venues/{v.id}")
        assert rid.status_code == 200 and rid.json()["name"] == "Lab Club"
        assert client.get("/venues/999999").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_list_events_filters_and_get(session):
    v = Venue(name="Audio", lat=-23.5, lng=-46.6, status="operational", confidence=60)
    session.add(v)
    session.flush()
    e = Event(name="Mamba Negra", starts_at=datetime(2099, 6, 13, 23, 0, tzinfo=SP),
              venue_id=v.id, status="scheduled", genre="techno", confidence=80)
    session.add(e)
    session.flush()
    client = _client(session)
    try:
        r = client.get("/events", params={"min_confidence": 50, "genre": "techno"})
        assert r.status_code == 200
        assert "Mamba Negra" in [x["name"] for x in r.json()]

        # genre diferente exclui
        r2 = client.get("/events", params={"genre": "forro"})
        assert "Mamba Negra" not in [x["name"] for x in r2.json()]

        # bbox que NAO contem o venue exclui o evento
        r3 = client.get("/events", params={"bbox": "10,10,11,11"})
        assert "Mamba Negra" not in [x["name"] for x in r3.json()]

        rid = client.get(f"/events/{e.id}")
        assert rid.status_code == 200 and rid.json()["venue_id"] == v.id
        assert client.get("/events/999999").status_code == 404
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_api.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.api.main'`.

- [ ] **Step 3: Implementar a API**

Create `src/nightlife/api/__init__.py` (empty), then `src/nightlife/api/deps.py`:

```python
# src/nightlife/api/deps.py
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from ..db import SessionLocal


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
```

Then `src/nightlife/api/schemas.py`:

```python
# src/nightlife/api/schemas.py
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    category: str | None = None
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    status: str
    confidence: int
    is_monitored: bool


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    starts_at: datetime | None = None
    venue_id: int | None = None
    status: str
    genre: str | None = None
    ticket_url: str | None = None
    confidence: int
```

Then `src/nightlife/api/main.py`:

```python
# src/nightlife/api/main.py
from __future__ import annotations

from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Event, Venue
from .deps import get_session
from .schemas import EventOut, VenueOut

app = FastAPI(title="Nightlife SP — API")


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        min_lng, min_lat, max_lng, max_lat = (float(x) for x in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bbox deve ser 'minLng,minLat,maxLng,maxLat'") from exc
    return min_lng, min_lat, max_lng, max_lat


@app.get("/venues", response_model=list[VenueOut])
def list_venues(
    type: str | None = None,
    bbox: str | None = None,
    min_confidence: int = 0,
    session: Session = Depends(get_session),
):
    q = select(Venue).where(Venue.confidence >= min_confidence)
    if type is not None:
        q = q.where(Venue.category == type)
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = _parse_bbox(bbox)
        q = q.where(
            Venue.lat >= min_lat, Venue.lat <= max_lat,
            Venue.lng >= min_lng, Venue.lng <= max_lng,
        )
    return session.scalars(q.order_by(Venue.confidence.desc())).all()


@app.get("/venues/{venue_id}", response_model=VenueOut)
def get_venue(venue_id: int, session: Session = Depends(get_session)):
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue nao encontrado")
    return venue


@app.get("/events", response_model=list[EventOut])
def list_events(
    date_from: date | None = None,
    date_to: date | None = None,
    bbox: str | None = None,
    genre: str | None = None,
    min_confidence: int = 0,
    session: Session = Depends(get_session),
):
    q = select(Event).where(Event.confidence >= min_confidence)
    if date_from is not None:
        q = q.where(Event.starts_at >= date_from)
    if date_to is not None:
        q = q.where(Event.starts_at <= date_to)
    if genre is not None:
        q = q.where(Event.genre == genre)
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = _parse_bbox(bbox)
        q = q.join(Venue, Event.venue_id == Venue.id).where(
            Venue.lat >= min_lat, Venue.lat <= max_lat,
            Venue.lng >= min_lng, Venue.lng <= max_lng,
        )
    return session.scalars(q.order_by(Event.starts_at)).all()


@app.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="evento nao encontrado")
    return event
```

- [ ] **Step 4: Rodar e ver passar (suíte inteira)**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest -q -o console_output_style=count`
Expected: **55 passed** (53 anteriores + 2 da API).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/api/ tests/test_api.py && git commit -m "feat(api): FastAPI somente-leitura (/venues, /events com filtros+bbox, /{id})

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: Smoke da API (servidor sobe e responde)

**Files:** nenhum novo (verificação manual)

- [ ] **Step 1: Smoke — a API serve dados reais do banco**

Garanta schema + dados no banco de dev e bata nos endpoints via `TestClient` (sem override de `get_session`, então usa o banco real `nightlife`):

```bash
cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -c "from nightlife.db import engine, Base; import nightlife.models; Base.metadata.create_all(engine)" && .venv/Scripts/python -m nightlife.seed && .venv/Scripts/python -c "
from fastapi.testclient import TestClient
from nightlife.api.main import app
c = TestClient(app)
v = c.get('/venues', params={'min_confidence': 10}).json()
e = c.get('/events').json()
print('venues:', len(v), [x['name'] for x in v])
print('events:', len(e), [x['name'] for x in e])
"
```
Expected: `venues: 3 [...]` (Lab Club, Audio SP, Trackers) e `events: 3 [...]`. Prova que a API lê do banco real (não só do banco de teste).

> Esta task não tem commit (nenhum arquivo muda) — é só a prova de que a API serve dados reais.

---

## Task 3: Migrations Alembic

**Files:**
- Create: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/<rev>_initial.py` (gerado)
- Modify: `src/nightlife/seed.py` (remover o `create_all` do README/uso — opcional)

- [ ] **Step 1: Inicializar o Alembic**

```bash
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m alembic init migrations
```
Isso cria `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/`.

- [ ] **Step 2: Configurar `migrations/env.py`** — substitua o conteúdo gerado por:

```python
# migrations/env.py
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from nightlife.config import DATABASE_URL
from nightlife.db import Base
import nightlife.models  # noqa: F401 — registra os models no metadata

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Gerar a migration inicial contra um banco limpo**

A migration inicial deve descrever a criação de todo o schema. Como o banco de dev pode já ter as tabelas (criadas via `create_all`), limpe-as antes de autogerar para o Alembic captar o schema completo:

```bash
cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -c "from nightlife.db import engine, Base; import nightlife.models; Base.metadata.drop_all(engine); print('schema limpo')" && .venv/Scripts/python -m alembic revision --autogenerate -m "initial schema"
```
Expected: cria `migrations/versions/<rev>_initial_schema.py` com `op.create_table(...)` para as 8 tabelas. Abra o arquivo e confirme que ele cria `venues`, `venue_sources`, `organizers`, `events`, `event_sources`, `ingestion_runs`, `dedupe_candidates`, `verification_logs`.

- [ ] **Step 4: Aplicar e verificar**

```bash
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m alembic upgrade head && .venv/Scripts/python -c "from nightlife.db import engine; from sqlalchemy import inspect; print(sorted(inspect(engine).get_table_names()))"
```
Expected: `alembic upgrade head` roda sem erro; a lista de tabelas inclui as 8 + `alembic_version`. A suíte de testes continua em 55 (os testes usam `create_all` no `conftest`, independentes do Alembic): `.venv/Scripts/python -m pytest -q -o console_output_style=count`.

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add alembic.ini migrations/ && git commit -m "feat(db): migrations Alembic com schema inicial

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 4: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Criar `README.md`**

```markdown
# Nightlife App

Backend pessoal que descobre, verifica, deduplica e expõe **venues e eventos** de vida noturna de São Paulo (baladas, festas, eventos, festivais) — com evidência, rastreio de fonte e score de confiança. O valor está na camada de dados confiável; a interface (lista + mapa) consome a API.

> Não busca 100% de cobertura: o sistema mede a própria cobertura, frescor e verificação. Respeita robots.txt / termos das fontes e não coleta dados pessoais de participantes.

## Arquitetura (4 camadas)

1. **Catálogo** — descobre venues (Google Places / OSM / listas) → `venues` com geo.
2. **Canais** — acha IG / site / ticketing de cada venue → `venue_sources`.
3. **Eventos** — extrai eventos dos canais monitorados (JSON-LD / HTML / flyer) → `events` ancorados no venue.
4. **Saída** — API REST (lista + mapa via bbox).

Camadas de código:
- `domain/` — lógica pura: datas PT-BR, scoring, matching, dedupe.
- `extraction/` — JSON-LD / HTML / texto livre → `ExtractedEvent`.
- `persistence/` — modelos SQLAlchemy + repositórios (`upsert_venue`, `upsert_event`).
- `ingestion/` — fontes + pipeline (`run_ingestion`).
- `api/` — FastAPI.

## Rodando

Requer Python 3.12+ e Docker.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Windows; Linux/mac: .venv/bin/python

docker compose up -d --wait                        # Postgres+PostGIS (porta 5434)
.venv/Scripts/python -m alembic upgrade head       # cria o schema
.venv/Scripts/python -m nightlife.seed             # popula com dados mock
.venv/Scripts/python -m uvicorn nightlife.api.main:app --reload --port 8001
```

Endpoints: `GET /venues?type=&bbox=&min_confidence=`, `GET /events?date_from=&date_to=&bbox=&genre=&min_confidence=`, `GET /venues/{id}`, `GET /events/{id}`. `bbox` = `minLng,minLat,maxLng,maxLat`.

## Testes

```bash
docker compose up -d --wait
.venv/Scripts/python -m pytest -q -o console_output_style=count
```

## Como adicionar uma fonte

1. Implemente o protocolo `Source` (`ingestion/base.py`): métodos `venues()` e `event_pages()` devolvendo `RawVenue` / `RawEventPage`.
2. Mapeie o `source_type` em `ingestion/signals.py` para os sinais de scoring corretos.
3. Para um novo formato de página, adicione um ramo em `_extract_page` (`ingestion/pipeline.py`) reusando um extractor de `extraction/`.
4. Rode a fonte via `run_ingestion(session, sua_fonte, reference=...)`.

A fonte mock (`ingestion/mock_source.py` + `fixtures/`) é o exemplo de referência.

## Status

Esqueleto (walking skeleton) completo com dados mock: domínio + persistência + ingestão + API, com testes. Fontes reais (Places/OSM/ticketing/Instagram), extração multimodal de flyers, Telegram e a UI de lista/mapa são os próximos passos.
```

- [ ] **Step 2: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add README.md && git commit -m "docs: README (arquitetura, como rodar, como adicionar fonte)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Coverage map (Plano D ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §8 endpoints `GET /venues`, `GET /events` (filtros + bbox) | Task 1 |
| §8 `GET /venues/{id}`, `GET /events/{id}` | Task 1 |
| Database schema/**migrations** | Task 3 |
| README explicando arquitetura e como adicionar fontes | Task 4 |

**Fora do Plano D (futuro):** endpoints de admin/merge (no spec viram ações de Telegram), fontes reais, vision multimodal, Telegram, UI de lista/mapa, métricas de coverage/freshness expostas, decay temporal.
