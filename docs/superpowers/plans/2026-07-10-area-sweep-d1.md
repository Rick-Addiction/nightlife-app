# Ciclo D-1: Varredura de IG por Área — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Varrer os handles de IG de uma área (CLI `--bairro` ou círculo escolhido no mapa), encadear a extração dos flyers, ancorar eventos por handle quando o nome não resolver, e responder na UI com progresso, diff ("+N festas · +M locais com pin") e tabela-relatório por local.

**Architecture:** Spec `docs/superpowers/specs/2026-07-10-area-sweep-design.md`. Backend: ancoragem por handle no pipeline (fallback do nome; organizer nunca ancora) + `handles_in_area` no `ig_state` + modelo `AreaSweep` (report/diff JSONB) + runner encadeado `nightlife.sweep_area` (scrape→visão→diff, blindado, injetável p/ teste) + `POST/GET /admin/area-sweeps` (subprocesso destacado, lock de 1 run). Frontend: `MapView` ganha modo-alvo e círculo (props opcionais); `MapaTab` orquestra o fluxo (picking→confirm→running com poll 5s→diff) e abre a tabela `SweepReport`.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic + pytest; React 19 + TS + Vitest; sem dependência nova.

**Referências verificadas do código atual (2026-07-10, master pós C-2):**
- `ingestion/base.py`: `RawEvent` (dataclass; tem `venue_name` que só ANCORA, nunca cria).
- `ingestion/pipeline.py::run_ingestion`: bloco `for rev in raw_events:` — `rev.venue` → upsert; `elif rev.venue_name:` → `_resolve_venue` (match por nome). É AQUI que entra o fallback por handle.
- `extraction/flyer.py::flyer_to_raw_event(extraction, image_hash, *, reference, permalink=None)` → RawEvent; `ingestion/flyer_source.py::FlyerSource.events()` lê sidecar `{caption, permalink}` (o sidecar TAMBÉM tem `handle` — hoje ignorado).
- `persistence/ig_state.py`: `handles_to_scrape` (relevance+platform+pausa), `scrape_queue(cap)`, `get_or_create_state`, `record_success/failure`, `record_venue_activity`. `IgProfileState {handle, last_shortcode, last_scraped_at, consecutive_failures}`.
- `ingest_ig.py::main`: `open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)` → loop `scrape_handle(handle, last_shortcode=..., fetch_posts=..., download=..., config=ScrapeConfig(inbox, cap))` → `result.downloaded/.last_shortcode/.latest_post_at` → commit + sleep 4-11s.
- `ingest_flyers.py::main`: `FlyerSource(FLYERS_DIR, CodexExtractor(), reference=date.today())` → `run_ingestion(label="flyers")` → `_move_all(processed_paths, FLYERS_DIR/"processed")` etc.
- `domain/matching.py:51`: `_haversine_km(lat1, lng1, lat2, lng2)` privado — expor alias público.
- `ingestion/places_source.py`: `SEED_POINTS: list[(nome, lat, lng)]` (20 sementes).
- Última migration: `e5f6a7b8c9d0` (venue_ig_last_post_at). Padrão em `migrations/versions/e5f6a7b8c9d0_*.py`.
- `api/main.py`: só GETs; `deps.get_session` (yield); Pydantic schemas em `api/schemas.py`. `_IG_PERMALINK = re.compile(r"instagram\.com/p/([A-Za-z0-9_-]+)")` já existe.
- `web/vite.config.ts`: proxy `/api` → :8001 com rewrite que TIRA o prefixo → frontend chama `/api/admin/area-sweeps`.
- `web/src/api/client.ts`: só `getJson`/`buildQuery` — precisa de `postJson`.
- `web/src/data/bairros.ts`: `distanceKm(aLat,aLng,bLat,bLng)` exportado (reusar no front).
- `web/src/tabs/MapaTab.tsx`: composição MapView + chips overlay + CAMADAS + Drawer; testes MOCKAM `../map/MapView` (canvas não roda em jsdom).
- `web/src/map/MapView.tsx`: `onMapClick` interno p/ popup de venue; `interactiveLayerIds`; Sources/Layers GL.
- `web/src/App.tsx`: tem `reloadKey`/`setReloadKey` (bump = refetch) e passa props pro MapaTab.
- Testes: backend `.venv/Scripts/python -m pytest <arq> -v` (Postgres 5434 up; suíte cheia com `--basetemp=.pytest-tmp`, deletar depois); web `cd web && npx vitest run <arq>` + `npx tsc -b`.

**Convenção de commit:** trailer `Claude-Session: b9eb4ce7-361b-434d-9809-31614b56e56d`. **Branch:** `feat/area-sweep-d1`.

---

### Task 1: Ancoragem por handle no pipeline

**Files:**
- Modify: `src/nightlife/ingestion/base.py` (RawEvent), `src/nightlife/extraction/flyer.py`, `src/nightlife/ingestion/flyer_source.py`, `src/nightlife/ingestion/pipeline.py`
- Test: `tests/test_handle_anchor.py` (novo)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_handle_anchor.py
"""Ancoragem por handle: flyer postado pelo IG do proprio venue ancora nele
quando o nome escrito no flyer nao resolve. Organizer NUNCA ancora."""
from datetime import date

from nightlife.ingestion.base import RawEvent
from nightlife.ingestion.pipeline import run_ingestion
from nightlife.models import Event, Organizer, Venue


class _FakeSource:
    def __init__(self, events):
        self._events = events
    def venues(self):
        return []
    def event_pages(self):
        return []
    def events(self):
        return self._events


def _raw(name="Festa X", venue_name=None, source_handle=None):
    return RawEvent(name=name, source_type="vision_flyer",
                    venue_name=venue_name, source_handle=source_handle,
                    source_url="https://www.instagram.com/p/ABC123/")


def test_handle_de_venue_ancora_quando_nome_nao_resolve(session):
    v = Venue(name="Selva Club", instagram="selva.011", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    run_ingestion(session, _FakeSource([_raw(source_handle="selva.011")]),
                  reference=date(2026, 7, 10), label="flyers")
    ev = session.query(Event).filter_by(name="Festa X").one()
    assert ev.venue_id == v.id


def test_nome_que_resolve_tem_prioridade_sobre_handle(session):
    certo = Venue(name="Blitz Haus", lat=-23.552, lng=-46.652, confidence=50)
    dono = Venue(name="Selva Club", instagram="selva.011", lat=-23.55, lng=-46.65, confidence=50)
    session.add_all([certo, dono])
    session.flush()
    run_ingestion(session, _FakeSource([_raw(venue_name="Blitz Haus", source_handle="selva.011")]),
                  reference=date(2026, 7, 10), label="flyers")
    ev = session.query(Event).filter_by(name="Festa X").one()
    assert ev.venue_id == certo.id


def test_handle_de_organizer_nao_ancora(session):
    org = Organizer(name="Mamba Negra", instagram="mambanegra")
    session.add(org)
    session.flush()
    run_ingestion(session, _FakeSource([_raw(source_handle="mambanegra")]),
                  reference=date(2026, 7, 10), label="flyers")
    ev = session.query(Event).filter_by(name="Festa X").one()
    assert ev.venue_id is None


def test_handle_ambiguo_escolhe_maior_confianca(session):
    a = Venue(name="Dup A", instagram="dupclub", confidence=30)
    b = Venue(name="Dup B", instagram="dupclub", confidence=70)
    session.add_all([a, b])
    session.flush()
    run_ingestion(session, _FakeSource([_raw(source_handle="dupclub")]),
                  reference=date(2026, 7, 10), label="flyers")
    ev = session.query(Event).filter_by(name="Festa X").one()
    assert ev.venue_id == b.id
```

(Confira em `tests/conftest.py` a fixture `session` e os kwargs obrigatórios de `Venue`/`Organizer`/`Event`; ajuste kwargs sem mudar as asserções.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_handle_anchor.py -v`
Expected: FAIL — `RawEvent` não tem `source_handle` (TypeError no dataclass)

- [ ] **Step 3: Implement**

`base.py` — acrescente ao dataclass `RawEvent` (depois de `venue_name`):

```python
    source_handle: str | None = None    # @ do IG que POSTOU (venue proprio) — fallback de ancora
```

`pipeline.py` — helper novo (perto de `_resolve_venue`) e uso no bloco `for rev in raw_events:`:

```python
def _venue_by_handle(session: Session, handle: str | None) -> Venue | None:
    """Venue dono do handle (fallback de ancoragem). So VENUES — organizer
    posta festa em casa alheia, ancorar nele erraria o lugar. Handle
    duplicado (venues ainda nao deduplicados): fica o de maior confianca."""
    if not handle:
        return None
    return session.scalars(
        select(Venue).where(Venue.instagram == handle)
        .order_by(Venue.confidence.desc(), Venue.id)
    ).first()
```

e no loop, logo depois do `elif rev.venue_name:` (mantendo o comportamento atual):

```python
            elif rev.venue_name:
                # flyer da nome sem geo (e com typo): ancora no catalogo, nunca cria
                venue = _resolve_venue(session, rev.venue_name)
            if venue is None:
                # nome nao resolveu (ou nem veio): flyer postado pelo IG do
                # proprio venue ancora nele (Ciclo D-1)
                venue = _venue_by_handle(session, rev.source_handle)
```

`flyer.py` — `flyer_to_raw_event` ganha `handle: str | None = None` na assinatura e repassa `source_handle=handle` no `RawEvent(...)`.

`flyer_source.py` — no `events()`, leia também o handle do sidecar e repasse:

```python
            caption = permalink = handle = None
            if sidecar.exists():
                try:
                    meta = json.loads(sidecar.read_text(encoding="utf-8"))
                    caption = meta.get("caption")
                    permalink = meta.get("permalink")
                    handle = meta.get("handle")
                except (ValueError, OSError):
                    pass
            ...
            raw_event = flyer_to_raw_event(extraction, image_hash,
                                           reference=self._reference,
                                           permalink=permalink, handle=handle)
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_handle_anchor.py tests/test_flyer_source.py tests/test_pipeline.py -v` (rode os arquivos de teste existentes que cobrem pipeline/flyer — ajuste nomes se diferirem via `ls tests/`)
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/ingestion/base.py src/nightlife/ingestion/pipeline.py src/nightlife/extraction/flyer.py src/nightlife/ingestion/flyer_source.py tests/test_handle_anchor.py
git commit -m "feat(pipeline): ancoragem por handle do IG — fallback quando o nome do flyer nao resolve"
```

---

### Task 2: Backfill dos eventos flutuantes (one-off)

**Files:**
- Create: `src/nightlife/backfill_handle_anchor.py`
- Test: `tests/test_backfill_handle_anchor.py`

Os 22 eventos de flyer já criados SEM venue não passam de novo pelo pipeline (flyers estão em `processed/`). Runner one-off: p/ cada evento com `venue_id IS NULL` e evidência `vision_flyer` com permalink IG, acha o sidecar `processed/{shortcode}.json`, pega o handle e ancora via `_venue_by_handle`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backfill_handle_anchor.py
import json
from datetime import datetime, timezone

from nightlife.backfill_handle_anchor import backfill
from nightlife.models import Event, EventSource, Venue


def test_backfill_ancora_evento_flutuante_pelo_sidecar(session, tmp_path):
    v = Venue(name="Aura Club", instagram="aura.clubsp", lat=-23.55, lng=-46.66, confidence=50)
    session.add(v)
    session.flush()
    ev = Event(name="Expand Your Aura", status="scheduled", confidence=40,
               starts_at=datetime(2099, 7, 11, 2, 0, tzinfo=timezone.utc))
    session.add(ev)
    session.flush()
    session.add(EventSource(event_id=ev.id, source_type="vision_flyer",
                            source_url="https://www.instagram.com/p/DagZZD/"))
    session.flush()
    (tmp_path / "DagZZD.json").write_text(json.dumps({"handle": "aura.clubsp"}), encoding="utf-8")

    n = backfill(session, processed_dir=tmp_path)

    assert n == 1
    assert ev.venue_id == v.id


def test_backfill_ignora_sem_sidecar_e_ja_ancorado(session, tmp_path):
    v = Venue(name="X", instagram="x", confidence=50)
    session.add(v)
    session.flush()
    ok = Event(name="Ja ancorado", status="scheduled", confidence=40, venue_id=v.id)
    solto = Event(name="Sem sidecar", status="scheduled", confidence=40)
    session.add_all([ok, solto])
    session.flush()
    session.add(EventSource(event_id=solto.id, source_type="vision_flyer",
                            source_url="https://www.instagram.com/p/NAOEXISTE/"))
    session.flush()
    assert backfill(session, processed_dir=tmp_path) == 0
    assert solto.venue_id is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_backfill_handle_anchor.py -v --basetemp=.pytest-tmp`
Expected: FAIL (módulo não existe)

- [ ] **Step 3: Implement**

```python
# src/nightlife/backfill_handle_anchor.py
"""One-off: ancora eventos de flyer que ficaram sem venue, via handle do
sidecar em flyers/processed/ (a ancoragem por handle so passou a existir no
pipeline no Ciclo D-1). Uso: .venv/Scripts/python -m nightlife.backfill_handle_anchor"""
from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .ingestion.pipeline import _venue_by_handle
from .models import Event, EventSource

_IG_PERMALINK = re.compile(r"instagram\.com/p/([A-Za-z0-9_-]+)")
PROCESSED_DIR = Path("flyers") / "processed"


def backfill(session: Session, *, processed_dir: Path = PROCESSED_DIR) -> int:
    anchored = 0
    rows = session.execute(
        select(Event, EventSource.source_url)
        .join(EventSource, EventSource.event_id == Event.id)
        .where(Event.venue_id.is_(None), EventSource.source_type == "vision_flyer",
               EventSource.source_url.is_not(None))
    ).all()
    for event, url in rows:
        m = _IG_PERMALINK.search(url or "")
        if not m:
            continue
        sidecar = processed_dir / f"{m.group(1)}.json"
        if not sidecar.exists():
            continue
        try:
            handle = json.loads(sidecar.read_text(encoding="utf-8")).get("handle")
        except (ValueError, OSError):
            continue
        venue = _venue_by_handle(session, handle)
        if venue is not None and event.venue_id is None:
            event.venue_id = venue.id
            anchored += 1
    return anchored


def main() -> None:
    with SessionLocal() as session:
        n = backfill(session)
        session.commit()
        print(f"ancorados: {n} eventos")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_backfill_handle_anchor.py -v --basetemp=.pytest-tmp` → PASS (delete `.pytest-tmp`)

- [ ] **Step 5: Rodar o backfill REAL e conferir**

```bash
.venv/Scripts/python -m nightlife.backfill_handle_anchor
```
Expected: `ancorados: N eventos` com N ≥ 15 (dos 22 flutuantes, os de handle de venue; os de organizer — ex. flyers da @mambanegra — ficam soltos por design). Anote N no report.

- [ ] **Step 6: Commit**

```bash
git add src/nightlife/backfill_handle_anchor.py tests/test_backfill_handle_anchor.py
git commit -m "feat: backfill one-off — ancora eventos de flyer flutuantes pelo handle do sidecar"
```

---

### Task 3: `handles_in_area` + alias público do haversine

**Files:**
- Modify: `src/nightlife/domain/matching.py` (alias), `src/nightlife/persistence/ig_state.py`
- Test: `tests/test_ig_state.py` (acrescentar; confira o nome real com `ls tests/ | grep ig`)

- [ ] **Step 1: Write the failing tests** (acrescentar ao arquivo de testes do ig_state)

```python
def test_handles_in_area_filtra_por_raio_e_ordena_por_antiguidade(session):
    from datetime import datetime, timezone
    from nightlife.persistence.ig_state import get_or_create_state, handles_in_area
    from nightlife.models import Venue
    dentro_novo = Venue(name="Blitz Haus", instagram="blitzhaus", lat=-23.552, lng=-46.652, confidence=50)
    dentro_velho = Venue(name="Netao", instagram="netao", lat=-23.5517, lng=-46.6516, confidence=50)
    fora = Venue(name="D-Edge", instagram="dedge", lat=-23.5207, lng=-46.6663, confidence=50)
    sem_geo = Venue(name="Fantasma", instagram="fantasma", confidence=50)
    buffet = Venue(name="Buffet Alegria Kids", instagram="alegriakids", lat=-23.552, lng=-46.653, confidence=50)
    session.add_all([dentro_novo, dentro_velho, fora, sem_geo, buffet])
    session.flush()
    st = get_or_create_state(session, "netao")
    st.last_scraped_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    session.flush()

    out = handles_in_area(session, -23.553, -46.656, 2.0)

    # nunca-varrido primeiro, depois o mais antigo; fora do raio/sem geo/buffet ficam fora
    assert out == ["blitzhaus", "netao"]


def test_handles_in_area_exclui_pausados(session):
    from nightlife.persistence.ig_state import get_or_create_state, handles_in_area
    from nightlife.models import Venue
    v = Venue(name="Pausado Club", instagram="pausado", lat=-23.553, lng=-46.656, confidence=50)
    session.add(v)
    session.flush()
    st = get_or_create_state(session, "pausado")
    st.consecutive_failures = 3
    session.flush()
    assert handles_in_area(session, -23.553, -46.656, 2.0) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_ig_state.py -v` → FAIL (função não existe)

- [ ] **Step 3: Implement**

`matching.py` — alias público logo após a definição de `_haversine_km`:

```python
haversine_km = _haversine_km  # uso fora do matching (fila por area do IG)
```

`ig_state.py` — nova função (imports: `from ..domain.matching import haversine_km` e `venue_relevance`/`is_platform_handle` já importados):

```python
def handles_in_area(session: Session, lat: float, lng: float, km: float,
                    *, pause_threshold: int = 3) -> list[str]:
    """Handles de VENUES dentro do raio, SEM cap (decisao do spec D-1: area
    varre tudo de uma vez). Nunca-varrido primeiro, depois o mais antigo.
    Exclui platform-handles, pausados e venues 'blocked' (buffet) — mas
    INCLUI dormants: em modo area o objetivo e descoberta (bar da Augusta
    com festa no IG e exatamente o que buscamos). Organizers ficam fora
    (nao tem geo)."""
    venues = session.scalars(select(Venue).where(
        Venue.instagram.is_not(None), Venue.lat.is_not(None), Venue.lng.is_not(None),
    )).all()
    with_events = set(session.scalars(
        select(Event.venue_id).where(Event.venue_id.is_not(None))).all())
    inside = {
        v.instagram for v in venues
        if haversine_km(lat, lng, v.lat, v.lng) <= km
        and not is_platform_handle(v.instagram)
        and venue_relevance(v.name, v.category, v.id in with_events, v.is_monitored,
                            has_contact=True,
                            business_status=v.business_status) != "blocked"
    }
    paused = set(session.scalars(
        select(IgProfileState.handle)
        .where(IgProfileState.consecutive_failures >= pause_threshold)).all())
    scraped_at = {st.handle: st.last_scraped_at
                  for st in session.scalars(select(IgProfileState))}
    epoch = datetime.min.replace(tzinfo=timezone.utc)

    def _staleness(h: str):
        ts = scraped_at.get(h)
        return (ts is not None, ts or epoch, h)

    return sorted(inside - paused, key=_staleness)
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_ig_state.py tests/test_matching.py -v` → PASS (ajuste nome do arquivo de matching se diferir)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/domain/matching.py src/nightlife/persistence/ig_state.py tests/test_ig_state.py
git commit -m "feat(ig): handles_in_area — fila por raio sem cap, nunca-varrido primeiro, buffet fora"
```

---

### Task 4: Modelo `AreaSweep` + migration

**Files:**
- Modify: `src/nightlife/models.py`
- Create: `migrations/versions/f6a7b8c9d0e1_area_sweeps.py`

- [ ] **Step 1: Modelo** — em `models.py` (siga o estilo dos modelos vizinhos; importe `JSONB` de `sqlalchemy.dialects.postgresql` se ainda não houver):

```python
class AreaSweep(Base):
    __tablename__ = "area_sweeps"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str | None] = mapped_column(String(100), default=None)   # ex. "augusta"
    center_lat: Mapped[float] = mapped_column(Float)
    center_lng: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="running")     # running|done|error
    phase: Mapped[str] = mapped_column(String(20), default="iniciando")    # iniciando|varrendo|extraindo|done
    total_handles: Mapped[int] = mapped_column(Integer, default=0)
    pid: Mapped[int | None] = mapped_column(Integer, default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    report: Mapped[list] = mapped_column(JSONB, default=list)   # [{venue_id, venue_name, handle, status, posts_novos, flyers, festas}]
    diff: Mapped[dict | None] = mapped_column(JSONB, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
```

- [ ] **Step 2: Migration** — `migrations/versions/f6a7b8c9d0e1_area_sweeps.py` no padrão do arquivo `e5f6a7b8c9d0_*` (copie o esqueleto; `revision='f6a7b8c9d0e1'`, `down_revision='e5f6a7b8c9d0'`):

```python
def upgrade() -> None:
    op.create_table(
        "area_sweeps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lng", sa.Float(), nullable=False),
        sa.Column("radius_km", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("phase", sa.String(length=20), nullable=False, server_default="iniciando"),
        sa.Column("total_handles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("diff", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("area_sweeps")
```

- [ ] **Step 3: Aplicar e verificar**

```bash
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -c "from nightlife.db import SessionLocal; from nightlife.models import AreaSweep; from sqlalchemy import select; s=SessionLocal(); print(s.scalars(select(AreaSweep)).all())"
```
Expected: `[]` (tabela existe, vazia). O banco de TESTE ganha a tabela via o mecanismo que o conftest usa (confira: se o conftest cria schema por metadata, nada a fazer; se roda alembic, idem).

- [ ] **Step 4: Commit**

```bash
git add src/nightlife/models.py migrations/versions/f6a7b8c9d0e1_area_sweeps.py
git commit -m "feat(db): modelo AreaSweep (report/diff JSONB) + migration f6a7b8c9d0e1"
```

---

### Task 5: Runner `nightlife.sweep_area` (núcleo injetável + CLI)

**Files:**
- Create: `src/nightlife/sweep_area.py`
- Test: `tests/test_sweep_area.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sweep_area.py
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from nightlife.models import AreaSweep, Event, Venue
from nightlife.sweep_area import compute_diff, resolve_bairro, run_sweep


def test_resolve_bairro_normaliza_e_casa_substring():
    label, lat, lng = resolve_bairro("augusta")
    assert "Augusta" in label
    assert lat == pytest.approx(-23.55, abs=0.02)
    with pytest.raises(ValueError):
        resolve_bairro("atlantida")   # inexistente lista os validos


def test_compute_diff_conta_festas_novas_e_venues_com_primeiro_pin(session):
    v_novo = Venue(name="Aura", instagram="aura", lat=-23.55, lng=-46.66, confidence=50)
    v_velho = Venue(name="Blitz", instagram="blitz", lat=-23.552, lng=-46.652, confidence=50)
    session.add_all([v_novo, v_velho])
    session.flush()
    antes_evt = Event(name="Antiga", status="scheduled", confidence=40, venue_id=v_velho.id,
                      starts_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
    session.add(antes_evt)
    session.flush()
    from nightlife.sweep_area import snapshot_future
    before = snapshot_future(session)
    nova1 = Event(name="Nova no Aura", status="scheduled", confidence=40, venue_id=v_novo.id,
                  starts_at=datetime(2099, 2, 1, tzinfo=timezone.utc))
    nova2 = Event(name="Nova no Blitz", status="scheduled", confidence=40, venue_id=v_velho.id,
                  starts_at=datetime(2099, 2, 2, tzinfo=timezone.utc))
    session.add_all([nova1, nova2])
    session.flush()
    diff = compute_diff(session, before)
    assert diff["novas_festas"] == 2
    assert diff["venues_com_pin_novo"] == ["Aura"]   # Blitz ja tinha festa


def test_run_sweep_preenche_report_e_nao_derruba_por_handle_com_falha(session, tmp_path):
    v1 = Venue(name="Aura", instagram="aura", lat=-23.55, lng=-46.66, confidence=50)
    v2 = Venue(name="Quebrado", instagram="quebrado", lat=-23.551, lng=-46.661, confidence=50)
    session.add_all([v1, v2])
    session.flush()
    sweep = AreaSweep(center_lat=-23.55, center_lng=-46.66, radius_km=2.0,
                      started_at=datetime.now(timezone.utc))
    session.add(sweep)
    session.flush()

    def fake_scrape(handle, state):
        if handle == "quebrado":
            raise RuntimeError("boom")
        (tmp_path / "SC1.jpg").write_bytes(b"x")
        (tmp_path / "SC1.json").write_text('{"handle": "aura"}')
        return SimpleNamespace(downloaded=1, last_shortcode="SC1",
                               latest_post_at=datetime.now(timezone.utc))

    def fake_extract():
        # simula a extracao criando um evento ancorado com permalink do SC1
        from nightlife.models import EventSource
        ev = Event(name="Festa do Aura", status="scheduled", confidence=40, venue_id=v1.id,
                   starts_at=datetime(2099, 3, 1, tzinfo=timezone.utc))
        session.add(ev)
        session.flush()
        session.add(EventSource(event_id=ev.id, source_type="vision_flyer",
                                source_url="https://www.instagram.com/p/SC1/"))
        session.flush()

    run_sweep(session, sweep, inbox=tmp_path, scrape=fake_scrape, extract=fake_extract,
              delay=lambda: None)

    assert sweep.status == "done"
    assert sweep.phase == "done"
    assert sweep.total_handles == 2
    by_handle = {i["handle"]: i for i in sweep.report}
    assert by_handle["aura"]["status"] == "ok"
    assert by_handle["aura"]["posts_novos"] == 1
    assert by_handle["aura"]["flyers"] == ["SC1"]
    assert by_handle["aura"]["festas"][0]["name"] == "Festa do Aura"
    assert by_handle["aura"]["festas"][0]["anchored"] is True
    assert by_handle["quebrado"]["status"] == "falha"
    assert sweep.diff["novas_festas"] == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_sweep_area.py -v --basetemp=.pytest-tmp` → FAIL (módulo não existe)

- [ ] **Step 3: Implement**

```python
# src/nightlife/sweep_area.py
"""Varredura de IG por AREA (Ciclo D-1): scrape de todos os handles do
circulo (sem cap — decisao do spec), extracao dos flyers, diff e report
por local. CLI: --bairro <nome> [--km 2] | --center lat,lng --km r
[--sweep-id N (uso da API)]."""
from __future__ import annotations

import argparse
import random
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import config
from .db import SessionLocal
from .ingestion.places_source import SEED_POINTS
from .models import AreaSweep, Event, EventSource, Venue
from .persistence.ig_state import (
    get_or_create_state, handles_in_area, record_failure, record_success,
    record_venue_activity,
)

FLYERS_DIR = Path("flyers")
DEFAULT_KM = 2.0


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) != "Mn")


def resolve_bairro(nome: str) -> tuple[str, float, float]:
    """Match por substring normalizada contra as sementes; 1o match vence.
    Nenhum match -> ValueError listando os validos."""
    alvo = _norm(nome)
    for label, lat, lng in SEED_POINTS:
        if alvo in _norm(label):
            return label, lat, lng
    validos = ", ".join(label for label, _, _ in SEED_POINTS)
    raise ValueError(f"bairro {nome!r} nao encontrado. Validos: {validos}")


def snapshot_future(session: Session) -> dict:
    """Estado 'antes' pro diff: ids de eventos futuros e venues que ja tem festa."""
    now = datetime.now(timezone.utc)
    events = set(session.scalars(select(Event.id).where(Event.starts_at > now)).all())
    venues = set(session.scalars(
        select(Event.venue_id).where(Event.starts_at > now, Event.venue_id.is_not(None))).all())
    return {"event_ids": events, "venue_ids": venues}


def compute_diff(session: Session, before: dict) -> dict:
    now = datetime.now(timezone.utc)
    events = set(session.scalars(select(Event.id).where(Event.starts_at > now)).all())
    venue_ids = set(session.scalars(
        select(Event.venue_id).where(Event.starts_at > now, Event.venue_id.is_not(None))).all())
    ganharam = venue_ids - before["venue_ids"]
    nomes = sorted(session.scalars(select(Venue.name).where(Venue.id.in_(ganharam))).all()) if ganharam else []
    return {"novas_festas": len(events - before["event_ids"]),
            "venues_com_pin_novo": nomes}


def _events_for_shortcodes(session: Session, shortcodes: list[str]) -> list[dict]:
    out: list[dict] = []
    for sc in shortcodes:
        rows = session.execute(
            select(Event).join(EventSource, EventSource.event_id == Event.id)
            .where(EventSource.source_type == "vision_flyer",
                   EventSource.source_url.like(f"%/p/{sc}%"))
        ).scalars().all()
        for ev in rows:
            out.append({"event_id": ev.id, "name": ev.name,
                        "starts_at": ev.starts_at.isoformat() if ev.starts_at else None,
                        "anchored": ev.venue_id is not None})
    return out


def run_sweep(session: Session, sweep: AreaSweep, *, inbox: Path,
              scrape: Callable, extract: Callable[[], None],
              delay: Callable[[], None]) -> None:
    """Nucleo testavel: scrape/extract/delay injetaveis. Blindado por handle."""
    before = snapshot_future(session)
    handles = handles_in_area(session, sweep.center_lat, sweep.center_lng, sweep.radius_km)
    venues_by_handle = {v.instagram: v for v in session.scalars(
        select(Venue).where(Venue.instagram.in_(handles)))} if handles else {}
    sweep.total_handles = len(handles)
    sweep.phase = "varrendo"
    session.commit()

    for handle in handles:
        st = get_or_create_state(session, handle)
        v = venues_by_handle.get(handle)
        item = {"venue_id": v.id if v else None, "venue_name": v.name if v else None,
                "handle": handle, "status": "ok", "posts_novos": 0,
                "flyers": [], "festas": []}
        stems_before = {p.stem for p in inbox.glob("*.json")}
        try:
            result = scrape(handle, st)
            record_success(st, result.last_shortcode)
            record_venue_activity(session, handle, result.latest_post_at)
            item["posts_novos"] = result.downloaded
            item["flyers"] = sorted({p.stem for p in inbox.glob("*.json")} - stems_before)
        except Exception as exc:  # noqa: BLE001 — falha isolada por handle
            record_failure(st)
            item["status"] = "falha"
            item["erro"] = str(exc)[:300]
        sweep.report = [*sweep.report, item]
        flag_modified(sweep, "report")
        session.commit()
        delay()

    sweep.phase = "extraindo"
    session.commit()
    try:
        extract()
    except Exception as exc:  # noqa: BLE001 — extracao inteira falhou: reporta, nao trava
        sweep.error = f"extracao: {exc}"[:500]
    # casa festas criadas de volta aos itens (por shortcode do permalink)
    report = sweep.report
    for item in report:
        if item["flyers"]:
            item["festas"] = _events_for_shortcodes(session, item["flyers"])
    sweep.report = report
    flag_modified(sweep, "report")
    sweep.diff = compute_diff(session, before)
    sweep.phase = "done"
    sweep.status = "error" if sweep.error else "done"
    sweep.finished_at = datetime.now(timezone.utc)
    session.commit()


def _real_scrape_factory(context):
    from .ingestion.instagram_source import (
        ScrapeConfig, playwright_download, playwright_fetch_posts, scrape_handle,
    )

    def _scrape(handle, st):
        cap = (config.IG_MAX_POSTS_FIRST_SWEEP if st.last_shortcode is None
               else config.IG_MAX_POSTS_INCREMENTAL)
        return scrape_handle(
            handle, last_shortcode=st.last_shortcode,
            fetch_posts=lambda h: playwright_fetch_posts(context, h),
            download=lambda p, d: playwright_download(context, p, d),
            config=ScrapeConfig(inbox=FLYERS_DIR, cap=cap),
        )
    return _scrape


def _real_extract(session: Session) -> None:
    import shutil
    from .ingest_flyers import _move_all
    from .ingestion.codex_extractor import CodexExtractor
    from .ingestion.flyer_source import FlyerSource
    from .ingestion.pipeline import run_ingestion
    if shutil.which("codex") is None:
        raise RuntimeError("codex CLI nao encontrado no PATH")
    source = FlyerSource(FLYERS_DIR, CodexExtractor(), reference=date.today())
    run_ingestion(session, source, reference=date.today(), label="flyers")
    session.commit()
    _move_all(source.processed_paths, FLYERS_DIR / "processed")
    _move_all(source.failed_paths, FLYERS_DIR / "failed")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bairro")
    g.add_argument("--center", help="lat,lng")
    ap.add_argument("--km", type=float, default=DEFAULT_KM)
    ap.add_argument("--sweep-id", type=int, default=None, help="registro criado pela API")
    args = ap.parse_args(argv)

    FLYERS_DIR.mkdir(exist_ok=True)
    with SessionLocal() as session:
        if args.sweep_id is not None:
            sweep = session.get(AreaSweep, args.sweep_id)
            if sweep is None:
                raise SystemExit(f"AreaSweep #{args.sweep_id} nao existe")
        else:
            running = session.scalars(
                select(AreaSweep).where(AreaSweep.status == "running")).first()
            if running is not None:
                raise SystemExit(f"ja existe varredura rodando (#{running.id}) — aguarde ou "
                                 f"marque status='error' manualmente se ela morreu")
            if args.bairro:
                label, lat, lng = resolve_bairro(args.bairro)
            else:
                lat, lng = (float(x) for x in args.center.split(","))
                label = None
            sweep = AreaSweep(label=label, center_lat=lat, center_lng=lng,
                              radius_km=args.km, started_at=datetime.now(timezone.utc))
            session.add(sweep)
            session.commit()

        from .ingestion.instagram_source import open_context
        pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
        try:
            run_sweep(session, sweep, inbox=FLYERS_DIR,
                      scrape=_real_scrape_factory(context),
                      extract=lambda: _real_extract(session),
                      delay=lambda: time.sleep(random.uniform(config.IG_DELAY_MIN,
                                                              config.IG_DELAY_MAX)))
        except Exception as exc:  # noqa: BLE001 — marca o sweep, nao deixa running orfao
            sweep.status = "error"
            sweep.error = str(exc)[:500]
            sweep.finished_at = datetime.now(timezone.utc)
            session.commit()
            raise
        finally:
            context.close()
            pw.stop()
        d = sweep.diff or {}
        print(f"sweep #{sweep.id} {sweep.status}: +{d.get('novas_festas', 0)} festas, "
              f"venues com pin novo: {d.get('venues_com_pin_novo', [])}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_sweep_area.py -v --basetemp=.pytest-tmp` → PASS (delete `.pytest-tmp`). Rode também a suíte de ig_state.

- [ ] **Step 5: Smoke do CLI (sem IG real)**

```bash
.venv/Scripts/python -m nightlife.sweep_area --bairro atlantida
```
Expected: erro listando os bairros válidos (prova o wiring de argparse sem tocar o IG).

- [ ] **Step 6: Commit**

```bash
git add src/nightlife/sweep_area.py tests/test_sweep_area.py
git commit -m "feat: runner sweep_area — varredura por area encadeada com report por local e diff"
```

---

### Task 6: Endpoints `/admin/area-sweeps`

**Files:**
- Modify: `src/nightlife/api/main.py`, `src/nightlife/api/schemas.py`
- Test: `tests/test_api_area_sweeps.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_area_sweeps.py
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from nightlife.api.deps import get_session
from nightlife.api.main import app
from nightlife.models import AreaSweep


def _client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def test_post_cria_sweep_e_spawna_subprocesso(session, monkeypatch):
    spawned = {}
    monkeypatch.setattr("nightlife.api.main._spawn_sweep",
                        lambda sweep_id: spawned.setdefault("id", sweep_id) or 4242)
    client = _client(session)
    try:
        r = client.post("/admin/area-sweeps", json={"lat": -23.553, "lng": -46.656, "km": 2.0})
        assert r.status_code == 202
        sweep_id = r.json()["id"]
        assert spawned["id"] == sweep_id
        sw = session.get(AreaSweep, sweep_id)
        assert sw.status == "running"
        assert sw.pid == 4242
    finally:
        app.dependency_overrides.clear()


def test_post_409_se_ja_ha_running(session, monkeypatch):
    monkeypatch.setattr("nightlife.api.main._spawn_sweep", lambda sweep_id: 1)
    session.add(AreaSweep(center_lat=-23.5, center_lng=-46.6, radius_km=2,
                          status="running", started_at=datetime.now(timezone.utc)))
    session.flush()
    client = _client(session)
    try:
        r = client.post("/admin/area-sweeps", json={"lat": -23.5, "lng": -46.6, "km": 1.0})
        assert r.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_get_current_devolve_ultimo_com_report_e_diff(session):
    session.add(AreaSweep(center_lat=-23.5, center_lng=-46.6, radius_km=2, status="done",
                          phase="done", total_handles=2,
                          started_at=datetime.now(timezone.utc),
                          report=[{"handle": "aura", "status": "ok", "posts_novos": 1,
                                   "flyers": ["SC1"], "festas": [], "venue_id": 1,
                                   "venue_name": "Aura"}],
                          diff={"novas_festas": 1, "venues_com_pin_novo": ["Aura"]}))
    session.flush()
    client = _client(session)
    try:
        r = client.get("/admin/area-sweeps/current")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "done"
        assert body["diff"]["novas_festas"] == 1
        assert body["report"][0]["handle"] == "aura"
        assert body["done_handles"] == 1
    finally:
        app.dependency_overrides.clear()


def test_get_current_404_sem_nenhum(session):
    client = _client(session)
    try:
        assert client.get("/admin/area-sweeps/current").status_code == 404
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_api_area_sweeps.py -v` → FAIL (404 nas rotas)

- [ ] **Step 3: Implement**

`schemas.py`:

```python
class AreaSweepIn(BaseModel):
    lat: float
    lng: float
    km: float = 2.0


class AreaSweepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    label: str | None = None
    status: str
    phase: str
    total_handles: int
    done_handles: int = 0
    report: list = []
    diff: dict | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
```

`main.py` (imports: `sys`, `subprocess`, `os`, `AreaSweep`, `AreaSweepIn/Out`):

```python
def _spawn_sweep(sweep_id: int) -> int:
    """Subprocesso DESTACADO (sobrevive a API): o runner faz o trabalho."""
    cmd = [sys.executable, "-m", "nightlife.sweep_area", "--sweep-id", str(sweep_id),
           "--center", "0,0"]  # center ignorado quando --sweep-id existe
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    log = open(f"logs/sweep_{sweep_id}.log", "ab")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=flags, close_fds=True)
    return proc.pid


@app.post("/admin/area-sweeps", status_code=202)
def start_area_sweep(body: AreaSweepIn, session: Session = Depends(get_session)):
    running = session.scalars(select(AreaSweep).where(AreaSweep.status == "running")).first()
    if running is not None:
        raise HTTPException(status_code=409,
                            detail=f"varredura #{running.id} ja esta rodando")
    sweep = AreaSweep(center_lat=body.lat, center_lng=body.lng, radius_km=body.km,
                      started_at=datetime.now(timezone.utc))
    session.add(sweep)
    session.flush()
    sweep.pid = _spawn_sweep(sweep.id)
    session.commit()
    return {"id": sweep.id}


@app.get("/admin/area-sweeps/current", response_model=AreaSweepOut)
def get_current_sweep(session: Session = Depends(get_session)):
    sweep = session.scalars(select(AreaSweep).order_by(AreaSweep.id.desc())).first()
    if sweep is None:
        raise HTTPException(status_code=404, detail="nenhuma varredura ainda")
    out = AreaSweepOut.model_validate(sweep)
    out.done_handles = len(sweep.report or [])
    return out
```

Atenção: no `sweep_area.main`, o argparse tem grupo mutuamente exclusivo required — com `--sweep-id` o `--center 0,0` dummy satisfaz o grupo e é ignorado (o registro já tem centro). Garanta `logs/` existente (`Path("logs").mkdir(exist_ok=True)` antes do `open`). O `get_session` do deps não commita sozinho — o `session.commit()` explícito no POST é necessário (confira `deps.py`).

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_api_area_sweeps.py tests/test_api.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/api/main.py src/nightlife/api/schemas.py tests/test_api_area_sweeps.py
git commit -m "feat(api): POST/GET /admin/area-sweeps — dispara subprocesso destacado com lock de 1 run"
```

---

### Task 7: Web — client `api/sweep.ts` + `postJson` + helpers de círculo

**Files:**
- Modify: `web/src/api/client.ts`
- Create: `web/src/api/sweep.ts`, `web/src/map/sweep.ts`
- Test: `web/src/map/sweep.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/map/sweep.test.ts
import { describe, it, expect } from 'vitest'
import { circleGeoJSON, handlesInCircle } from './sweep'
import type { VenueOut } from '../api/types'

function venue(id: number, lat: number | null, lng: number | null, ig: string | null): VenueOut {
  return { id, name: `V${id}`, category: null, lat, lng, address: null, instagram: ig,
           website: null, status: 'active', confidence: 50, effective_confidence: 50,
           is_monitored: false, ig_last_post_at: null, places_verified: false }
}

describe('circleGeoJSON', () => {
  it('gera poligono fechado com steps+1 pontos em volta do centro', () => {
    const f = circleGeoJSON(-23.553, -46.656, 2, 32)
    expect(f.geometry.type).toBe('Polygon')
    const ring = f.geometry.coordinates[0]
    expect(ring).toHaveLength(33)
    expect(ring[0]).toEqual(ring[32])   // fechado
    // raio ~2km: todo ponto entre 1.9 e 2.1 km do centro (haversine simples)
    for (const [lng, lat] of ring.slice(0, 32)) {
      const R = 6371, rad = (x: number) => (x * Math.PI) / 180
      const dLat = rad(lat - -23.553), dLng = rad(lng - -46.656)
      const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(-23.553)) * Math.cos(rad(lat)) * Math.sin(dLng / 2) ** 2
      const d = 2 * R * Math.asin(Math.sqrt(h))
      expect(d).toBeGreaterThan(1.9)
      expect(d).toBeLessThan(2.1)
    }
  })
})

describe('handlesInCircle', () => {
  it('conta so venues com instagram e geo dentro do raio', () => {
    const vs = [
      venue(1, -23.552, -46.652, 'blitzhaus'),   // dentro (~450m)
      venue(2, -23.52, -46.666, 'dedge'),        // fora (~3.8km)
      venue(3, -23.553, -46.656, null),          // sem IG
      venue(4, null, null, 'semgeo'),            // sem geo
    ]
    expect(handlesInCircle(vs, -23.553, -46.656, 2)).toBe(1)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/map/sweep.test.ts` → FAIL (módulo não existe)

- [ ] **Step 3: Implement**

`web/src/map/sweep.ts`:

```ts
import type { Feature, Polygon } from 'geojson'
import type { VenueOut } from '../api/types'
import { distanceKm } from '../data/bairros'

// circulo geodesico aproximado (bom o suficiente pra ~5km em SP)
export function circleGeoJSON(lat: number, lng: number, km: number, steps = 64): Feature<Polygon> {
  const ring: [number, number][] = []
  const dLat = km / 110.574
  const dLng = km / (111.32 * Math.cos((lat * Math.PI) / 180))
  for (let i = 0; i < steps; i++) {
    const t = (i / steps) * 2 * Math.PI
    ring.push([lng + dLng * Math.cos(t), lat + dLat * Math.sin(t)])
  }
  ring.push(ring[0])
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } }
}

export function handlesInCircle(venues: VenueOut[], lat: number, lng: number, km: number): number {
  return venues.filter((v) =>
    v.instagram != null && v.lat != null && v.lng != null &&
    distanceKm(lat, lng, v.lat, v.lng) <= km).length
}
```

`web/src/api/client.ts` — acrescente:

```ts
export async function postJson<T>(url: string, body: unknown): Promise<T> {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw new Error(`API ${resp.status} em ${url}`)
  return resp.json() as Promise<T>
}
```

`web/src/api/sweep.ts`:

```ts
import { getJson, postJson } from './client'
```

(Se `getJson` não for exportado em `client.ts`, exporte-o.) E:

```ts
export interface SweepFesta { event_id: number; name: string; starts_at: string | null; anchored: boolean }
export interface SweepItem {
  venue_id: number | null; venue_name: string | null; handle: string
  status: 'ok' | 'falha'; posts_novos: number; flyers: string[]; festas: SweepFesta[]; erro?: string
}
export interface SweepOut {
  id: number; label: string | null; status: 'running' | 'done' | 'error'
  phase: 'iniciando' | 'varrendo' | 'extraindo' | 'done'
  total_handles: number; done_handles: number
  report: SweepItem[]; diff: { novas_festas: number; venues_com_pin_novo: string[] } | null
  error: string | null; started_at: string; finished_at: string | null
}

export function startSweep(lat: number, lng: number, km: number): Promise<{ id: number }> {
  return postJson('/api/admin/area-sweeps', { lat, lng, km })
}

export function fetchCurrentSweep(): Promise<SweepOut> {
  return getJson<SweepOut>('/api/admin/area-sweeps/current')
}
```

- [ ] **Step 4: Run tests**

Run: `cd web && npx vitest run src/map/sweep.test.ts && npx tsc -b` → PASS. (Se `geojson` types não resolverem, `Feature`/`Polygon` vêm de `geojson` que já é dependência transitiva do maplibre; senão declare os tipos localmente.)

- [ ] **Step 5: Commit**

```bash
git add web/src/api/client.ts web/src/api/sweep.ts web/src/map/sweep.ts web/src/map/sweep.test.ts
git commit -m "feat(web): client de area-sweep + circleGeoJSON/handlesInCircle"
```

---

### Task 8: Web — MapView ganha modo-alvo e círculo (props opcionais)

**Files:**
- Modify: `web/src/map/MapView.tsx`

Sem teste unitário (canvas GL; verificado por tsc + smoke — padrão do projeto). Mudança mínima:

- [ ] **Step 1: Props novas**

```tsx
export function MapView({ events, venues, selectedId, onSelect, showVenues,
                          onPickPoint, circle }: {
  events: EventWithGeo[]; venues: VenueOut[]; selectedId: number | null
  onSelect: (id: number) => void; showVenues: boolean
  onPickPoint?: (lat: number, lng: number) => void
  circle?: { lat: number; lng: number; km: number } | null
}) {
```

No `onMapClick`, ANTES da lógica de venue:

```tsx
  const onMapClick = (e: MapLayerMouseEvent) => {
    if (onPickPoint) {
      onPickPoint(e.lngLat.lat, e.lngLat.lng)
      return
    }
    ...
```

Depois dos Sources existentes, o círculo (import `circleGeoJSON` de `./sweep`):

```tsx
      {circle && (
        <Source id="sweep-circle-src" type="geojson"
                data={circleGeoJSON(circle.lat, circle.lng, circle.km)}>
          <Layer id="sweep-circle-fill" type="fill"
                 paint={{ 'fill-color': '#ff2e88', 'fill-opacity': 0.12 }} />
          <Layer id="sweep-circle-line" type="line"
                 paint={{ 'line-color': '#ff2e88', 'line-width': 2 }} />
        </Source>
      )}
```

(Lembrete do projeto: ids de Layer DISTINTOS do id do Source.)

- [ ] **Step 2: Verify**

Run: `cd web && npx tsc -b && npx vitest run` → limpo/verde (MapaTab.test mocka o MapView, não quebra).

- [ ] **Step 3: Commit**

```bash
git add web/src/map/MapView.tsx
git commit -m "feat(web): MapView — modo-alvo (onPickPoint) e circulo de varredura (props opcionais)"
```

---

### Task 9: Web — fluxo de varredura no MapaTab (alvo → confirmar → rodar → diff → tabela)

**Files:**
- Create: `web/src/components/SweepPanel.tsx`, `web/src/components/SweepReport.tsx`
- Modify: `web/src/tabs/MapaTab.tsx`, `web/src/App.tsx`
- Test: `web/src/components/SweepPanel.test.tsx`, `web/src/components/SweepReport.test.tsx`, `web/src/tabs/MapaTab.test.tsx` (acrescentar)

Estado no MapaTab: `sweepUi: 'idle' | 'picking' | { lat, lng, km } (confirm)`. O sweep corrente vem de poll (5s) em `fetchCurrentSweep` — ativo enquanto `status==='running'`; quando transiciona pra done/error → `onDataStale()` (novo prop, vindo do App = bump do `reloadKey`).

- [ ] **Step 1: Write the failing tests**

```tsx
// web/src/components/SweepPanel.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SweepPanel } from './SweepPanel'
import type { SweepOut } from '../api/sweep'

const runningSweep: SweepOut = {
  id: 1, label: null, status: 'running', phase: 'varrendo', total_handles: 66,
  done_handles: 12, report: [], diff: null, error: null,
  started_at: '2026-07-10T20:00:00Z', finished_at: null,
}
const doneSweep: SweepOut = {
  ...runningSweep, status: 'done', phase: 'done', done_handles: 66,
  diff: { novas_festas: 9, venues_com_pin_novo: ['Aura', 'Selva Club'] }, finished_at: '2026-07-10T21:00:00Z',
}

describe('SweepPanel', () => {
  it('confirmacao mostra contagem e dispara onConfirm com o raio do slider', async () => {
    const onConfirm = vi.fn()
    render(<SweepPanel mode={{ lat: -23.553, lng: -46.656, km: 2 }} count={41}
                       sweep={null} onConfirm={onConfirm} onCancel={() => {}}
                       onKm={() => {}} onOpenReport={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'VARRER 41 PERFIS →' }))
    expect(onConfirm).toHaveBeenCalled()
  })
  it('fase varrendo mostra progresso', () => {
    render(<SweepPanel mode="idle" count={0} sweep={runningSweep}
                       onConfirm={() => {}} onCancel={() => {}} onKm={() => {}} onOpenReport={() => {}} />)
    expect(screen.getByText(/VARRENDO 12\/66/)).toBeInTheDocument()
  })
  it('done mostra o diff e abre o relatorio', async () => {
    const onOpenReport = vi.fn()
    render(<SweepPanel mode="idle" count={0} sweep={doneSweep}
                       onConfirm={() => {}} onCancel={() => {}} onKm={() => {}} onOpenReport={onOpenReport} />)
    expect(screen.getByText(/\+9 FESTAS/)).toBeInTheDocument()
    expect(screen.getByText(/\+2 LOCAIS COM PIN/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'RELATÓRIO' }))
    expect(onOpenReport).toHaveBeenCalled()
  })
})
```

```tsx
// web/src/components/SweepReport.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SweepReport } from './SweepReport'
import type { SweepOut } from '../api/sweep'

const sweep: SweepOut = {
  id: 1, label: 'augusta', status: 'done', phase: 'done', total_handles: 2, done_handles: 2,
  report: [
    { venue_id: 1, venue_name: 'Aura Club', handle: 'aura.clubsp', status: 'ok',
      posts_novos: 3, flyers: ['SC1', 'SC2'],
      festas: [{ event_id: 9, name: 'Expand Your Aura', starts_at: '2026-07-11T02:00:00Z', anchored: true }] },
    { venue_id: 2, venue_name: 'Quebrado Bar', handle: 'quebrado', status: 'falha',
      posts_novos: 0, flyers: [], festas: [], erro: 'timeout' },
  ],
  diff: null, error: null, started_at: '2026-07-10T20:00:00Z', finished_at: null,
}

describe('SweepReport', () => {
  it('linha por local com handle, contagens, festas e marcador de ancora', () => {
    render(<SweepReport sweep={sweep} onClose={() => {}} />)
    expect(screen.getByText('Aura Club')).toBeInTheDocument()
    expect(screen.getByText('@aura.clubsp')).toBeInTheDocument()
    expect(screen.getByText('Expand Your Aura')).toBeInTheDocument()
    expect(screen.getByText('✓')).toBeInTheDocument()      // ancorada
    expect(screen.getByText('FALHA')).toBeInTheDocument()  // status do quebrado
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/components/SweepPanel.test.tsx src/components/SweepReport.test.tsx` → FAIL (módulos não existem)

- [ ] **Step 3: Implement components**

```tsx
// web/src/components/SweepPanel.tsx
import type { SweepOut } from '../api/sweep'

export type SweepMode = 'idle' | 'picking' | { lat: number; lng: number; km: number }

// painel flutuante do fluxo de varredura: confirmacao (circulo escolhido),
// progresso (poll) e diff final com acesso ao relatorio
export function SweepPanel({ mode, count, sweep, onConfirm, onCancel, onKm, onOpenReport }: {
  mode: SweepMode; count: number; sweep: SweepOut | null
  onConfirm: () => void; onCancel: () => void
  onKm: (km: number) => void; onOpenReport: () => void
}) {
  const wrap: React.CSSProperties = {
    position: 'absolute', left: 10, right: 10, bottom: 76, zIndex: 15,
    background: 'var(--black)', border: '2px solid var(--pink)', padding: 10,
  }
  if (typeof mode === 'object') {
    return (
      <div style={wrap}>
        <div className="label">RAIO: {mode.km.toFixed(1)} KM</div>
        <input type="range" min={0.5} max={5} step={0.5} value={mode.km}
               aria-label="RAIO" onChange={(e) => onKm(Number(e.target.value))}
               style={{ width: '100%', accentColor: 'var(--pink)' }} />
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button className="b-btn" style={{ width: 100 }} onClick={onCancel}>CANCELAR</button>
          <button className="b-btn primary" style={{ flex: 1 }} onClick={onConfirm}>
            {`VARRER ${count} PERFIS →`}
          </button>
        </div>
      </div>
    )
  }
  if (sweep?.status === 'running') {
    const txt = sweep.phase === 'extraindo'
      ? 'EXTRAINDO FLYERS…'
      : `VARRENDO ${sweep.done_handles}/${sweep.total_handles}`
    return (
      <div style={{ ...wrap, display: 'flex', alignItems: 'center', gap: 10 }}>
        <span className="label" style={{ color: 'var(--green)' }}>⌖ {txt}</span>
        <button className="chip" style={{ marginLeft: 'auto' }} onClick={onOpenReport}>PARCIAL</button>
      </div>
    )
  }
  if (sweep && (sweep.status === 'done' || sweep.status === 'error') && sweep.diff) {
    return (
      <div style={{ ...wrap, display: 'flex', alignItems: 'center', gap: 10 }}>
        <span className="label" style={{ color: 'var(--green)' }}>
          +{sweep.diff.novas_festas} FESTAS · +{sweep.diff.venues_com_pin_novo.length} LOCAIS COM PIN
        </span>
        <button className="chip grn" style={{ marginLeft: 'auto' }} onClick={onOpenReport}>RELATÓRIO</button>
        <button className="chip" onClick={onCancel}>✕</button>
      </div>
    )
  }
  return null
}
```

```tsx
// web/src/components/SweepReport.tsx
import type { SweepOut } from '../api/sweep'

export function SweepReport({ sweep, onClose }: { sweep: SweepOut; onClose: () => void }) {
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 45, background: 'rgba(0,0,0,0.75)' }}
         onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           style={{ position: 'absolute', left: 0, right: 0, bottom: 0, maxHeight: '88dvh',
                    overflowY: 'auto', background: 'var(--black)',
                    borderTop: '3px solid var(--green)', padding: '10px 12px 20px' }}>
        <div className="hline" style={{ fontSize: 20 }}>RELATÓRIO DA VARREDURA
          {sweep.label ? ` — ${sweep.label.toUpperCase()}` : ''}</div>
        <div className="label" style={{ margin: '4px 0 10px' }}>
          {sweep.done_handles}/{sweep.total_handles} PERFIS · STATUS {sweep.status.toUpperCase()}
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead>
              <tr className="label" style={{ textAlign: 'left' }}>
                <th style={{ padding: 4 }}>LOCAL</th><th>HANDLE</th><th>STATUS</th>
                <th>POSTS</th><th>FLYERS</th><th>FESTAS CRIADAS</th>
              </tr>
            </thead>
            <tbody>
              {sweep.report.map((i) => (
                <tr key={i.handle} style={{ borderTop: '1px solid var(--line)', verticalAlign: 'top' }}>
                  <td style={{ padding: 4, fontWeight: 800 }}>{i.venue_name ?? '—'}</td>
                  <td style={{ padding: 4, color: 'var(--muted)' }}>@{i.handle}</td>
                  <td style={{ padding: 4 }}>
                    {i.status === 'ok'
                      ? <span style={{ color: 'var(--green)', fontWeight: 800 }}>OK</span>
                      : <span style={{ color: 'var(--pink)', fontWeight: 800 }} title={i.erro}>FALHA</span>}
                  </td>
                  <td style={{ padding: 4 }}>{i.posts_novos}</td>
                  <td style={{ padding: 4 }}>{i.flyers.length}</td>
                  <td style={{ padding: 4 }}>
                    {i.festas.length === 0 && <span style={{ color: 'var(--dim)' }}>—</span>}
                    {i.festas.map((f) => (
                      <div key={f.event_id}>
                        <span>{f.anchored ? '✓' : '⚠'}</span> {f.name}
                        {f.starts_at && <span style={{ color: 'var(--muted)' }}>
                          {' '}({f.starts_at.slice(0, 10)})</span>}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Wire no MapaTab** — acrescente às props `onDataStale: () => void`; estado e lógica:

```tsx
  const [sweepUi, setSweepUi] = useState<SweepMode>('idle')
  const [sweep, setSweep] = useState<SweepOut | null>(null)
  const [reportOpen, setReportOpen] = useState(false)

  // poll do sweep corrente enquanto rodando; ao terminar, refetch dos dados
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const s = await fetchCurrentSweep()
        if (!alive) return
        setSweep((prev) => {
          if (prev?.status === 'running' && s.status !== 'running') onDataStale()
          return s
        })
      } catch { /* 404 = nunca varreu; silencio */ }
    }
    tick()
    const id = setInterval(() => {
      // poll continuo so enquanto ha run ativo (ou aguardando o 1o status)
      if (sweepRef.current?.status === 'running') tick()
    }, 5000)
    return () => { alive = false; clearInterval(id) }
  }, [onDataStale])
  const sweepRef = useRef(sweep)
  useEffect(() => { sweepRef.current = sweep }, [sweep])
```

(Se o lint reclamar da ordem ref/efeito, declare `sweepRef` antes do `useEffect`.) Botão e handlers:

- Junto do CAMADAS: `<button className={`chip${sweepUi !== 'idle' ? ' on' : ''}`} onClick={() => setSweepUi(sweepUi === 'idle' ? 'picking' : 'idle')}>⌖ VARRER ÁREA</button>`
- `MapView` recebe `onPickPoint={sweepUi === 'picking' ? (lat, lng) => setSweepUi({ lat, lng, km: 2 }) : undefined}` e `circle={typeof sweepUi === 'object' ? sweepUi : null}`.
- `count = typeof sweepUi === 'object' ? handlesInCircle(venues, sweepUi.lat, sweepUi.lng, sweepUi.km) : 0`.
- `SweepPanel` renderizado com `onConfirm={async () => { const c = sweepUi as {lat:number;lng:number;km:number}; await startSweep(c.lat, c.lng, c.km); setSweepUi('idle'); setSweep((s) => s ? { ...s, status: 'running', phase: 'iniciando', done_handles: 0, total_handles: 0, diff: null } : s); const first = await fetchCurrentSweep().catch(() => null); if (first) setSweep(first) }}`, `onCancel={() => { setSweepUi('idle'); setSweep((s) => s && s.status !== 'running' ? null : s) }}`, `onKm={(km) => setSweepUi((m) => typeof m === 'object' ? { ...m, km } : m)}`, `onOpenReport={() => setReportOpen(true)}`.
- `{reportOpen && sweep && <SweepReport sweep={sweep} onClose={() => setReportOpen(false)} />}`
- Erro no POST (409 etc.): capture e mostre `alert`? NÃO — sem alert (trava o claude-in-chrome); guarde `postError` num estado e exiba no SweepPanel de confirmação (linha vermelha pequena). Implemente `postError: string | null`.

Em `App.tsx`: `<MapaTab ... onDataStale={() => setReloadKey((k) => k + 1)} />`.

- [ ] **Step 5: Teste do MapaTab** — acrescente ao `MapaTab.test.tsx` (o mock do MapView já existe; mocke também o módulo `../api/sweep`):

```tsx
vi.mock('../api/sweep', () => ({
  startSweep: vi.fn(async () => ({ id: 1 })),
  fetchCurrentSweep: vi.fn(async () => { throw new Error('404') }),
}))

it('botao VARRER AREA entra em modo alvo e o clique confirma o circulo', async () => {
  render(<MapaTab {...base} onDataStale={() => {}} />)
  await userEvent.click(screen.getByRole('button', { name: '⌖ VARRER ÁREA' }))
  const last = mapProps.mock.calls.at(-1)![0] as { onPickPoint?: (a: number, b: number) => void }
  expect(last.onPickPoint).toBeDefined()
  act(() => last.onPickPoint!(-23.553, -46.656))
  expect(await screen.findByRole('button', { name: /VARRER \d+ PERFIS/ })).toBeInTheDocument()
})
```

(Importe `act` de `react`; a prop `onDataStale` entra no `base` das outras chamadas também.)

- [ ] **Step 6: Run tests + typecheck**

Run: `cd web && npx vitest run && npx tsc -b` → tudo verde.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/SweepPanel.tsx web/src/components/SweepPanel.test.tsx web/src/components/SweepReport.tsx web/src/components/SweepReport.test.tsx web/src/tabs/MapaTab.tsx web/src/tabs/MapaTab.test.tsx web/src/App.tsx
git commit -m "feat(web): fluxo de varredura no MapaTab — modo alvo, circulo, progresso com poll, diff e tabela"
```

---

### Task 10: Final — suítes completas + smoke real

- [ ] **Step 1:**

```bash
.venv/Scripts/python -m pytest -q --basetemp=.pytest-tmp   # backend inteiro (deletar .pytest-tmp)
cd web && npx vitest run && npx tsc -b && npm run build
```
Expected: tudo verde.

- [ ] **Step 2: Smoke (usuário)** — API :8001 + Vite no ar; no MAPA: ⌖ VARRER ÁREA → toque na Baixa Augusta → raio 2km → "VARRER N PERFIS →" (N ≈ 60+) → acompanhar chip (VARRENDO x/N → EXTRAINDO) → diff final → RELATÓRIO com a tabela → conferir pins novos na Augusta. CLI também: `python -m nightlife.sweep_area --bairro augusta`.
- [ ] **Step 3:** Smoke aprovado → finishing-a-development-branch (merge no master).

---

## Riscos & notas pro executor

- **NÃO rode IG real em teste** — o núcleo `run_sweep` é injetável justamente pra isso; o smoke real é do usuário.
- **`flag_modified` é obrigatório** ao mutar JSONB in-place (SQLAlchemy não detecta mutação de dict/list).
- **Subprocesso destacado:** o POST passa `--sweep-id`; o runner NÃO deve re-checar lock nesse caminho (o registro já é dele). `logs/` precisa existir antes do `open`.
- **Fixtures do conftest:** confira kwargs obrigatórios de modelos antes de escrever testes; ajuste kwargs, não asserções.
- **jsdom:** MapaTab.test MOCKA MapView e api/sweep; nunca renderize MapView real.
- **Sem `alert()`** na UI (trava a automação do navegador) — erros viram texto no painel.
- **Vite proxy:** front chama `/api/admin/...` (o rewrite tira o `/api`).
- **Deviação consciente do spec §3.5:** o chip mostra `EXTRAINDO FLYERS…` sem contador x/y — progresso por flyer exigiria hook invasivo dentro do loop do `FlyerSource` (YAGNI; o total de flyers aparece na tabela).
