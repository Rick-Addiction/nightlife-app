# Google Geocoding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Geocodar (endereço → lat/lng) os venues do RA que têm `address` mas não têm geo, via Google Geocoding API com cache, e rodar uma passada de re-dedup que funde os duplicados que agora têm geo para confirmar.

**Architecture:** Camadas puras e injetáveis. `geo_scope` (bbox SP, puro) + `geocoder` (cliente Google injetável, protocolo) + `geocode_cache` (tabela, idempotência entre runs) + `venue_merge` (merge de dois venues persistidos + passada de re-dedup) + runner `geocode_venues` (backfill + re-dedup + relatório), que entra no `daily.py`. Testes usam um geocoder fake — zero rede. Chave via `GOOGLE_MAPS_API_KEY`.

**Tech Stack:** Python 3.14, SQLAlchemy 2.0, psycopg3, httpx + truststore, Alembic, pytest, Postgres (porta 5434).

**Referências do código existente (assinaturas já verificadas):**
- `nightlife.domain.matching`: `VenueRef(id, name, address=None, lat=None, lng=None)`, `match_venue(candidate, existing, *, threshold=0.82) -> VenueMatch | None` (`.venue`, `.score`), `geo_distance_km(a, b) -> float | None`, `classify_venue_match(score, *, distance_km=None) -> "auto_merge"|"review"|"distinct"`.
- `nightlife.persistence.evidence.record_venue_evidence(session, venue_id, source: SourceInfo, *, contribution) -> VenueSource`.
- `nightlife.persistence.confidence.recompute_venue_confidence(session, venue, *, reference: date) -> int` e `VENUE_SOURCE_CONTRIBUTION` (dict).
- `nightlife.persistence.inputs.SourceInfo(source_type, source_url=None, raw_payload=None, extracted_fields=...)`.
- `nightlife.models`: `Venue(id, name, category, lat, lng, address, instagram, website, status, confidence, is_monitored, ...)`, `VenueSource(id, venue_id, source_type, source_url, ...)`, `Event(venue_id, ...)`, `DedupeCandidate(kind, a_id, b_id, similarity_score, decision)`.
- Testes: fixture `session` (rollback por teste) em `tests/conftest.py`; schema via `Base.metadata.create_all` (todo model novo em `models.py` precisa ser importado — `models.py` já é importado no conftest).
- `daily.py`: `STEPS: list[tuple[str, list[str]]]` com `(nome, [sys.executable, "-m", "nightlife.<modulo>"])`.
- Alembic: última migration `a1b2c3d4e5f6` (Revises `6db320547b8b`). A nova migration usa `down_revision = 'a1b2c3d4e5f6'`.

**Convenção de commit:** cada commit termina com o trailer `Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu`.

**Como rodar os testes:** `.venv/Scripts/python -m pytest <arquivo>::<teste> -v` (Postgres na 5434 precisa estar de pé).

---

### Task 1: `geo_scope.py` — bbox de SP (puro)

**Files:**
- Create: `src/nightlife/domain/geo_scope.py`
- Test: `tests/test_geo_scope.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geo_scope.py
from nightlife.domain.geo_scope import is_in_metro_sp, SP_METRO_BBOX


def test_ponto_em_sp_capital_e_dentro():
    # Praca da Se, centro de SP
    assert is_in_metro_sp(-23.5505, -46.6333) is True


def test_ponto_fora_de_sp_e_fora():
    # Itapema, Santa Catarina (o diretorio do RA arrastou)
    assert is_in_metro_sp(-27.0900, -48.6114) is False


def test_coordenada_ausente_e_fora():
    assert is_in_metro_sp(None, -46.6) is False
    assert is_in_metro_sp(-23.5, None) is False


def test_bbox_e_min_lat_max_lat_min_lng_max_lng():
    min_lat, max_lat, min_lng, max_lng = SP_METRO_BBOX
    assert min_lat < max_lat and min_lng < max_lng
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_geo_scope.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'nightlife.domain.geo_scope'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/nightlife/domain/geo_scope.py
"""Escopo geografico: 'este ponto esta na Regiao Metropolitana de SP?' (puro).

O diretorio do RA trouxe venues de outras cidades (Itapema/SC, Ubatuba). Depois
de geocodar, esta funcao permite filtrar por localizacao de verdade — coisa que
o texto do endereco nao dava. Usada no relatorio do runner de geocoding."""
from __future__ import annotations

# bbox aproximado da RMSP: (min_lat, max_lat, min_lng, max_lng).
# Cobre a Grande SP com folga (Guarulhos, ABC, Osasco, Barueri).
SP_METRO_BBOX: tuple[float, float, float, float] = (-24.10, -23.30, -47.10, -46.30)


def is_in_metro_sp(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    min_lat, max_lat, min_lng, max_lng = SP_METRO_BBOX
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_geo_scope.py -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/domain/geo_scope.py tests/test_geo_scope.py
git commit -m "feat: geo_scope.is_in_metro_sp (bbox RMSP, puro)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 2: `geocoder.py` — cliente Google injetável

**Files:**
- Create: `src/nightlife/ingestion/geocoder.py`
- Test: `tests/test_geocoder.py`

Contexto: o `GoogleGeocoder` faz uma chamada HTTP real, então o teste **não** o exercita contra a rede — testa o parsing via uma resposta JSON simulada (monkeypatch em `httpx.get`). O protocolo `Geocoder` + `GeocodeResult` são o contrato que o runner consome.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geocoder.py
import httpx

from nightlife.ingestion.geocoder import GoogleGeocoder, GeocodeResult


def _fake_response(payload):
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return payload
    return _Resp()


def test_status_ok_extrai_coordenadas(monkeypatch):
    payload = {"status": "OK", "results": [
        {"geometry": {"location": {"lat": -23.55, "lng": -46.63}}}
    ]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response(payload))
    res = GoogleGeocoder("KEY").geocode("Praca da Se, Sao Paulo")
    assert res == GeocodeResult(status="OK", lat=-23.55, lng=-46.63)


def test_zero_results_sem_coordenadas(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response({"status": "ZERO_RESULTS", "results": []}))
    res = GoogleGeocoder("KEY").geocode("endereco impossivel xyz")
    assert res == GeocodeResult(status="ZERO_RESULTS")


def test_over_query_limit_vira_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response({"status": "OVER_QUERY_LIMIT", "results": []}))
    res = GoogleGeocoder("KEY").geocode("qualquer")
    assert res.status == "ERROR"


def test_excecao_de_rede_vira_error(monkeypatch):
    def _boom(*a, **k): raise httpx.ConnectError("sem rede")
    monkeypatch.setattr(httpx, "get", _boom)
    res = GoogleGeocoder("KEY").geocode("qualquer")
    assert res.status == "ERROR"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_geocoder.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'nightlife.ingestion.geocoder'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/nightlife/ingestion/geocoder.py
"""Geocoding: endereco em texto -> coordenadas, via Google Geocoding API.

O protocolo Geocoder permite injetar um fake nos testes (zero rede). Status
mapeados: OK (coords), ZERO_RESULTS (endereco nao resolvido, cacheavel como
negativo), ERROR (transitorio: quota/rede/chave — NAO cacheia, tenta de novo)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

_ENDPOINT = "https://maps.googleapis.com/maps/api/geocode/json"
_TIMEOUT = 15.0


@dataclass(frozen=True)
class GeocodeResult:
    status: str                 # "OK" | "ZERO_RESULTS" | "ERROR"
    lat: float | None = None
    lng: float | None = None


class Geocoder(Protocol):
    def geocode(self, address: str) -> GeocodeResult: ...


class GoogleGeocoder:
    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def geocode(self, address: str) -> GeocodeResult:
        params = {
            "address": address,
            "key": self._key,
            "region": "br",
            "components": "country:BR",
        }
        try:
            resp = httpx.get(_ENDPOINT, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return GeocodeResult(status="ERROR")

        status = data.get("status")
        if status == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return GeocodeResult(status="OK", lat=loc["lat"], lng=loc["lng"])
        if status == "ZERO_RESULTS":
            return GeocodeResult(status="ZERO_RESULTS")
        return GeocodeResult(status="ERROR")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_geocoder.py -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/ingestion/geocoder.py tests/test_geocoder.py
git commit -m "feat: GoogleGeocoder + protocolo Geocoder (OK/ZERO_RESULTS/ERROR)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 3: model `GeocodeCache` + migration

**Files:**
- Modify: `src/nightlife/models.py` (adicionar o model no fim do arquivo)
- Create: `migrations/versions/c3d4e5f6a7b8_geocode_cache.py`
- Test: `tests/test_geocode_cache_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geocode_cache_model.py
from nightlife.models import GeocodeCache


def test_geocode_cache_persiste_e_le(session):
    session.add(GeocodeCache(address_norm="rua x, 1 sao paulo", status="OK",
                             lat=-23.5, lng=-46.6))
    session.flush()
    row = session.get(GeocodeCache, "rua x, 1 sao paulo")
    assert row is not None and row.status == "OK" and row.lat == -23.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_geocode_cache_model.py -v`
Expected: FAIL com `ImportError: cannot import name 'GeocodeCache'`

- [ ] **Step 3: Write minimal implementation**

Adicionar ao fim de `src/nightlife/models.py`:

```python
class GeocodeCache(Base):
    __tablename__ = "geocode_cache"
    address_norm: Mapped[str] = mapped_column(String(500), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))          # OK | ZERO_RESULTS
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lng: Mapped[float | None] = mapped_column(Float, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Criar a migration `migrations/versions/c3d4e5f6a7b8_geocode_cache.py`:

```python
"""geocode_cache: cache de endereco->coordenada

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-07-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'geocode_cache',
        sa.Column('address_norm', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('address_norm'),
    )


def downgrade() -> None:
    op.drop_table('geocode_cache')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_geocode_cache_model.py -v`
Expected: PASS (o conftest recria o schema via `create_all`, que enxerga o model novo)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/models.py migrations/versions/c3d4e5f6a7b8_geocode_cache.py tests/test_geocode_cache_model.py
git commit -m "feat: model GeocodeCache + migration

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 4: `geocode_cache.py` — normalização + lookup/store

**Files:**
- Create: `src/nightlife/persistence/geocode_cache.py`
- Test: `tests/test_geocode_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geocode_cache.py
from nightlife.ingestion.geocoder import GeocodeResult
from nightlife.persistence.geocode_cache import normalize_address, cache_lookup, cache_store
from nightlife.models import GeocodeCache
from sqlalchemy import select, func


def test_normalize_colapsa_espacos_e_caixa():
    assert normalize_address("  Rua  X,  1   São Paulo ") == "rua x, 1 são paulo"
    assert normalize_address("RUA X, 1 SÃO PAULO") == normalize_address("rua x, 1 são paulo")


def test_lookup_miss_retorna_none(session):
    assert cache_lookup(session, "rua inexistente") is None


def test_store_ok_e_recuperavel(session):
    cache_store(session, "Rua X, 1", GeocodeResult(status="OK", lat=-23.5, lng=-46.6))
    hit = cache_lookup(session, "rua x, 1")   # case-insensitive via normalize
    assert hit == GeocodeResult(status="OK", lat=-23.5, lng=-46.6)


def test_store_zero_results_e_cacheado_negativo(session):
    cache_store(session, "endereco ruim", GeocodeResult(status="ZERO_RESULTS"))
    hit = cache_lookup(session, "endereco ruim")
    assert hit == GeocodeResult(status="ZERO_RESULTS", lat=None, lng=None)


def test_store_error_nao_grava(session):
    cache_store(session, "transitorio", GeocodeResult(status="ERROR"))
    assert cache_lookup(session, "transitorio") is None
    n = session.scalar(select(func.count()).select_from(GeocodeCache))
    assert n == 0


def test_store_e_idempotente_no_mesmo_endereco(session):
    cache_store(session, "Rua Y, 2", GeocodeResult(status="OK", lat=-23.1, lng=-46.1))
    cache_store(session, "rua y, 2", GeocodeResult(status="OK", lat=-23.2, lng=-46.2))
    n = session.scalar(select(func.count()).select_from(GeocodeCache))
    assert n == 1  # mesma chave normalizada -> update, nao segunda linha
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_geocode_cache.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'nightlife.persistence.geocode_cache'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/nightlife/persistence/geocode_cache.py
"""Cache de geocoding (endereco normalizado -> coordenada), idempotente entre
runs. Garante que o mesmo endereco nunca e cobrado 2x na Google. ZERO_RESULTS e
cacheado como negativo (endereco ruim nao melhora sozinho); ERROR nao e gravado
(transitorio — tenta de novo no proximo run)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..ingestion.geocoder import GeocodeResult
from ..models import GeocodeCache


def normalize_address(address: str) -> str:
    return " ".join(address.split()).lower()


def cache_lookup(session: Session, address: str) -> GeocodeResult | None:
    row = session.get(GeocodeCache, normalize_address(address))
    if row is None:
        return None
    return GeocodeResult(status=row.status, lat=row.lat, lng=row.lng)


def cache_store(session: Session, address: str, result: GeocodeResult) -> None:
    if result.status == "ERROR":
        return  # transitorio: nao cacheia
    key = normalize_address(address)
    row = session.get(GeocodeCache, key)
    if row is None:
        row = GeocodeCache(address_norm=key)
        session.add(row)
    row.status = result.status
    row.lat = result.lat
    row.lng = result.lng
    session.flush()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_geocode_cache.py -v`
Expected: PASS (6 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/persistence/geocode_cache.py tests/test_geocode_cache.py
git commit -m "feat: geocode_cache (normalize/lookup/store, negative-cache)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 5: `venue_merge.merge_venues` — fundir dois venues persistidos

**Files:**
- Create: `src/nightlife/persistence/venue_merge.py`
- Test: `tests/test_venue_merge.py`

Contexto: `merge_venues` move a evidência e os eventos do `loser` para o `survivor`, preenche lacunas, recomputa confiança, apaga o loser e limpa os `DedupeCandidate` que o referenciam. A escolha de quem é survivor NÃO é feita aqui — é do chamador (Task 6). Este task entrega só o merge mecânico.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_venue_merge.py
from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue, VenueSource, Event, DedupeCandidate
from nightlife.persistence.venue_merge import merge_venues

REF = date(2026, 6, 1)


def _venue(session, name, **kw):
    v = Venue(name=name, **kw)
    session.add(v)
    session.flush()
    return v


def test_merge_move_evento_e_source_e_apaga_loser(session):
    survivor = _venue(session, "Mundo Pensante", lat=-23.55, lng=-46.63)
    loser = _venue(session, "Mundo Pensante", lat=-23.551, lng=-46.631)
    session.add(VenueSource(venue_id=loser.id, source_type="ra", source_url="https://ra.co/clubs/9"))
    ev = Event(name="Festa X", venue_id=loser.id)
    session.add(ev)
    session.flush()
    loser_id = loser.id

    merge_venues(session, survivor, loser, reference=REF)
    session.flush()

    assert session.get(Venue, loser_id) is None            # loser apagado
    assert session.get(Event, ev.id).venue_id == survivor.id  # evento movido
    moved = session.scalars(
        select(VenueSource).where(VenueSource.venue_id == survivor.id)
    ).all()
    assert any(s.source_type == "ra" and s.source_url == "https://ra.co/clubs/9" for s in moved)


def test_merge_nao_duplica_evidencia_igual(session):
    survivor = _venue(session, "D-Edge", lat=-23.5, lng=-46.6)
    loser = _venue(session, "D-Edge", lat=-23.5, lng=-46.6)
    # mesma evidencia (source_type, source_url) nos dois
    session.add(VenueSource(venue_id=survivor.id, source_type="ra", source_url="https://ra.co/clubs/1"))
    session.add(VenueSource(venue_id=loser.id, source_type="ra", source_url="https://ra.co/clubs/1"))
    session.flush()

    merge_venues(session, survivor, loser, reference=REF)
    session.flush()

    rows = session.scalars(
        select(VenueSource).where(
            VenueSource.venue_id == survivor.id,
            VenueSource.source_type == "ra",
            VenueSource.source_url == "https://ra.co/clubs/1",
        )
    ).all()
    assert len(rows) == 1  # nao virou linha dupla


def test_merge_preenche_lacunas_e_limpa_dedupe_candidate(session):
    survivor = _venue(session, "Selva", lat=-23.5, lng=-46.6)   # sem address
    loser = _venue(session, "Selva", lat=-23.5, lng=-46.6, address="Rua Augusta, 100", instagram="selvasp")
    session.add(DedupeCandidate(kind="venue", a_id=survivor.id, b_id=loser.id,
                                similarity_score=0.9, decision="review"))
    session.flush()
    loser_id = loser.id

    merge_venues(session, survivor, loser, reference=REF)
    session.flush()

    assert survivor.address == "Rua Augusta, 100"   # lacuna preenchida do loser
    assert survivor.instagram == "selvasp"
    remaining = session.scalars(
        select(DedupeCandidate).where(
            (DedupeCandidate.a_id == loser_id) | (DedupeCandidate.b_id == loser_id)
        )
    ).all()
    assert remaining == []   # candidatos do loser removidos
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_venue_merge.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'nightlife.persistence.venue_merge'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/nightlife/persistence/venue_merge.py
"""Fundir dois venues ja persistidos (survivor <- loser) e a passada de re-dedup
apos o geocoding. O upsert_venue so funde no momento da ingestao; aqui fundimos
duplicados que ja estao no banco e ganharam geo para confirmar o lugar fisico."""
from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..domain.matching import (
    VenueRef, classify_venue_match, geo_distance_km, match_venue,
)
from ..models import DedupeCandidate, Event, Venue, VenueSource
from .confidence import recompute_venue_confidence


def merge_venues(session: Session, survivor: Venue, loser: Venue, *, reference: date) -> Venue:
    # 1. evidencia do loser -> survivor, pulando (source_type, source_url) que o
    #    survivor ja tem (esses somem junto com o loser via cascade)
    existing = {
        (s.source_type, s.source_url)
        for s in session.scalars(select(VenueSource).where(VenueSource.venue_id == survivor.id))
    }
    for s in session.scalars(select(VenueSource).where(VenueSource.venue_id == loser.id)):
        if (s.source_type, s.source_url) not in existing:
            s.venue_id = survivor.id
            existing.add((s.source_type, s.source_url))

    # 2. eventos do loser -> survivor
    for e in session.scalars(select(Event).where(Event.venue_id == loser.id)):
        e.venue_id = survivor.id

    # 3. preenche lacunas do survivor a partir do loser
    if survivor.lat is None:
        survivor.lat, survivor.lng = loser.lat, loser.lng
    survivor.address = survivor.address or loser.address
    survivor.category = survivor.category or loser.category
    survivor.instagram = survivor.instagram or loser.instagram
    survivor.website = survivor.website or loser.website

    # 4. limpa DedupeCandidate que referenciam o loser (antes de apagar)
    for c in session.scalars(
        select(DedupeCandidate).where(
            or_(DedupeCandidate.a_id == loser.id, DedupeCandidate.b_id == loser.id)
        )
    ):
        session.delete(c)

    session.flush()
    session.delete(loser)          # cascade remove as VenueSource remanescentes do loser
    session.flush()
    recompute_venue_confidence(session, survivor, reference=reference)
    return survivor
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_venue_merge.py -v`
Expected: PASS (3 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/persistence/venue_merge.py tests/test_venue_merge.py
git commit -m "feat: merge_venues (funde dois venues persistidos, FK-safe)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 6: `rededup_geocoded` — re-avaliar os recém-geocodados

**Files:**
- Modify: `src/nightlife/persistence/venue_merge.py` (adicionar função no fim)
- Test: `tests/test_venue_merge.py` (adicionar testes)

Contexto: para cada venue recém-geocodado, procura o melhor match entre os **outros venues que têm geo**, classifica COM distância e funde (`auto_merge`) ou enfileira (`review`). Survivor = maior `confidence`; empate → menor `id`.

- [ ] **Step 1: Write the failing test**

```python
# adicionar em tests/test_venue_merge.py
from nightlife.persistence.venue_merge import rededup_geocoded


def test_rededup_funde_par_proximo_com_nome_igual(session):
    # A ja existente (mais confianca), B recem-geocodado a <1km, nome quase igual
    a = _venue(session, "Mundo Pensante", lat=-23.550, lng=-46.630, confidence=40)
    b = _venue(session, "Mundo Pensante", lat=-23.551, lng=-46.631, confidence=15)
    out = rededup_geocoded(session, [b.id], reference=REF)
    session.flush()
    assert out["merged"] == 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    assert session.get(Venue, a.id) is not None   # A (maior confianca) sobrevive
    assert session.get(Venue, b.id) is None


def test_rededup_faixa_review_enfileira_sem_fundir(session):
    # nomes parecidos mas nao identicos: name_similarity=0.706 (faixa review
    # [0.70,0.85)); a 0.60km (>0.15km -> sem boost geo, score fica em 0.706).
    a = _venue(session, "Trackers", lat=-23.550, lng=-46.630, confidence=30)
    b = _venue(session, "Trackings", lat=-23.554, lng=-46.634, confidence=15)
    out = rededup_geocoded(session, [b.id], reference=REF)
    session.flush()
    assert out["review"] >= 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 2   # nao fundiu
    cand = session.scalars(select(DedupeCandidate).where(DedupeCandidate.kind == "venue")).all()
    assert len(cand) == 1


def test_rededup_par_longe_nao_funde(session):
    a = _venue(session, "Selva", lat=-23.55, lng=-46.63, confidence=30)
    b = _venue(session, "Selva", lat=-23.20, lng=-46.10, confidence=15)  # >1km
    out = rededup_geocoded(session, [b.id], reference=REF)
    session.flush()
    assert out["merged"] == 0
    assert session.scalar(select(func.count()).select_from(Venue)) == 2


def test_rededup_ignora_venue_ja_fundido(session):
    # A e B iguais e proximos; passar os dois ids nao deve estourar ao processar
    # o segundo (que ja foi apagado no merge do primeiro)
    a = _venue(session, "D-Edge", lat=-23.550, lng=-46.630, confidence=15)
    b = _venue(session, "D-Edge", lat=-23.551, lng=-46.631, confidence=40)
    out = rededup_geocoded(session, [a.id, b.id], reference=REF)
    session.flush()
    assert out["merged"] == 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    assert session.get(Venue, b.id) is not None   # B (maior confianca) sobrevive
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_venue_merge.py -v -k rededup`
Expected: FAIL com `ImportError: cannot import name 'rededup_geocoded'`

- [ ] **Step 3: Write minimal implementation**

Adicionar ao fim de `src/nightlife/persistence/venue_merge.py`:

```python
def _ref(v: Venue) -> VenueRef:
    return VenueRef(v.id, v.name, v.address, v.lat, v.lng)


def _pick_survivor(a: Venue, b: Venue) -> tuple[Venue, Venue]:
    """survivor = maior confianca; empate -> menor id (mais antigo, tende a OSM)."""
    if (a.confidence, -a.id) >= (b.confidence, -b.id):
        return a, b
    return b, a


def rededup_geocoded(session: Session, geocoded_ids: list[int], *, reference: date) -> dict:
    """Re-avalia cada venue recem-geocodado contra os outros COM geo. auto_merge
    funde; review enfileira DedupeCandidate; distinct ignora."""
    counts = {"merged": 0, "review": 0, "distinct": 0}
    merged_away: set[int] = set()

    for vid in geocoded_ids:
        if vid in merged_away:
            continue
        venue = session.get(Venue, vid)
        if venue is None or venue.lat is None:
            continue

        others = session.scalars(
            select(Venue).where(Venue.id != vid, Venue.lat.is_not(None))
        ).all()
        if not others:
            continue
        best = match_venue(_ref(venue), [_ref(o) for o in others], threshold=0.0)
        if best is None:
            continue
        other = session.get(Venue, best.venue.id)
        decision = classify_venue_match(
            best.score, distance_km=geo_distance_km(_ref(venue), _ref(other))
        )

        if decision == "auto_merge":
            survivor, loser = _pick_survivor(venue, other)
            merge_venues(session, survivor, loser, reference=reference)
            merged_away.add(loser.id)
            counts["merged"] += 1
        elif decision == "review":
            exists = session.scalars(
                select(DedupeCandidate).where(
                    DedupeCandidate.kind == "venue",
                    or_(
                        (DedupeCandidate.a_id == venue.id) & (DedupeCandidate.b_id == other.id),
                        (DedupeCandidate.a_id == other.id) & (DedupeCandidate.b_id == venue.id),
                    ),
                )
            ).first()
            if exists is None:
                session.add(DedupeCandidate(
                    kind="venue", a_id=venue.id, b_id=other.id,
                    similarity_score=best.score, decision="review",
                ))
            counts["review"] += 1
        else:
            counts["distinct"] += 1

    session.flush()
    return counts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_venue_merge.py -v`
Expected: PASS (7 testes no total — 3 de merge + 4 de rededup)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/persistence/venue_merge.py tests/test_venue_merge.py
git commit -m "feat: rededup_geocoded (funde/enfileira recem-geocodados com geo)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 7: `config.GOOGLE_MAPS_API_KEY`

**Files:**
- Modify: `src/nightlife/config.py`
- Test: `tests/test_config_geocoding.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_geocoding.py
import importlib


def test_google_maps_api_key_le_do_ambiente(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "abc123")
    import nightlife.config as cfg
    importlib.reload(cfg)
    assert cfg.GOOGLE_MAPS_API_KEY == "abc123"


def test_google_maps_api_key_default_none(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    import nightlife.config as cfg
    importlib.reload(cfg)
    assert cfg.GOOGLE_MAPS_API_KEY is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_config_geocoding.py -v`
Expected: FAIL com `AttributeError: module 'nightlife.config' has no attribute 'GOOGLE_MAPS_API_KEY'`

- [ ] **Step 3: Write minimal implementation**

Adicionar ao fim de `src/nightlife/config.py`:

```python
# Google Geocoding API (endereco -> coordenada). Chave criada pelo usuario no
# Google Cloud (Geocoding API + billing). Sem ela, o runner de geocoding aborta.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY") or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_config_geocoding.py -v`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/config.py tests/test_config_geocoding.py
git commit -m "feat: config GOOGLE_MAPS_API_KEY

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 8: runner `geocode_venues` (backfill + re-dedup + relatório)

**Files:**
- Create: `src/nightlife/geocode_venues.py`
- Test: `tests/test_geocode_venues.py`

Contexto: `geocode_all(session, geocoder, *, reference)` é a lógica testável (recebe o geocoder injetado). `main()` é o entrypoint que lê a chave, monta o `GoogleGeocoder` real e commita. Testes exercitam `geocode_all` com um geocoder fake que conta chamadas.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geocode_venues.py
from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue, GeocodeCache
from nightlife.ingestion.geocoder import GeocodeResult
from nightlife.geocode_venues import geocode_all

REF = date(2026, 6, 1)


class FakeGeocoder:
    """Geocoder de teste: responde por endereco e conta chamadas."""
    def __init__(self, table):
        self.table = table          # dict endereco-substring -> GeocodeResult
        self.calls = 0

    def geocode(self, address):
        self.calls += 1
        for key, res in self.table.items():
            if key in address:
                return res
        return GeocodeResult(status="ZERO_RESULTS")


def _venue(session, name, address, **kw):
    v = Venue(name=name, address=address, **kw)
    session.add(v)
    session.flush()
    return v


def test_backfill_preenche_geo_dos_sem_geo(session):
    v = _venue(session, "D-Edge", "Alameda Olga, 170 Sao Paulo")
    g = FakeGeocoder({"Olga": GeocodeResult(status="OK", lat=-23.53, lng=-46.66)})
    out = geocode_all(session, g, reference=REF)
    session.flush()
    assert session.get(Venue, v.id).lat == -23.53
    assert out["geocoded"] == 1


def test_zero_results_fica_sem_geo(session):
    v = _venue(session, "Lugar Ruim", "endereco impossivel")
    g = FakeGeocoder({})   # tudo cai em ZERO_RESULTS
    geocode_all(session, g, reference=REF)
    session.flush()
    assert session.get(Venue, v.id).lat is None


def test_venue_sem_address_e_ignorado(session):
    v = _venue(session, "Sem Endereco", None)
    g = FakeGeocoder({"x": GeocodeResult(status="OK", lat=-23.5, lng=-46.6)})
    geocode_all(session, g, reference=REF)
    assert g.calls == 0   # nao chamou o geocoder


def test_rerun_usa_cache_e_nao_rechama(session):
    _venue(session, "D-Edge", "Alameda Olga, 170 Sao Paulo")
    g = FakeGeocoder({"Olga": GeocodeResult(status="OK", lat=-23.53, lng=-46.66)})
    geocode_all(session, g, reference=REF)
    session.flush()
    # segundo venue com o MESMO endereco, novo run: cache serve, geocoder nao e chamado de novo
    _venue(session, "D-Edge (dup)", "Alameda Olga, 170 Sao Paulo")
    calls_antes = g.calls
    geocode_all(session, g, reference=REF)
    assert g.calls == calls_antes   # 0 novas chamadas (cache hit)


def test_relatorio_conta_in_out_sp(session):
    _venue(session, "Em SP", "Rua A Sao Paulo")
    _venue(session, "Fora SP", "Rua B Itapema")
    g = FakeGeocoder({
        "Sao Paulo": GeocodeResult(status="OK", lat=-23.55, lng=-46.63),
        "Itapema": GeocodeResult(status="OK", lat=-27.09, lng=-48.61),
    })
    out = geocode_all(session, g, reference=REF)
    assert out["in_sp"] == 1 and out["out_sp"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_geocode_venues.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'nightlife.geocode_venues'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/nightlife/geocode_venues.py
"""Geocoda venues sem geo (endereco -> lat/lng) via Google e re-dedupa os que
ganharam geo. Backfill uma vez + passo diario, ambos com cache.

Uso: .venv/Scripts/python -m nightlife.geocode_venues
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain.geo_scope import is_in_metro_sp
from .ingestion.geocoder import Geocoder
from .models import Venue
from .persistence.geocode_cache import cache_lookup, cache_store
from .persistence.venue_merge import rededup_geocoded

_SP_TZ = ZoneInfo("America/Sao_Paulo")


def geocode_all(session: Session, geocoder: Geocoder, *, reference: date) -> dict:
    pend = session.scalars(
        select(Venue).where(Venue.lat.is_(None), Venue.address.is_not(None))
    ).all()

    geocoded_ids: list[int] = []
    in_sp = out_sp = zero = 0
    for v in pend:
        res = cache_lookup(session, v.address)
        if res is None:
            res = geocoder.geocode(v.address)
            cache_store(session, v.address, res)
        if res.status == "OK":
            v.lat, v.lng = res.lat, res.lng
            geocoded_ids.append(v.id)
            if is_in_metro_sp(res.lat, res.lng):
                in_sp += 1
            else:
                out_sp += 1
        else:
            zero += 1
    session.flush()

    dd = rededup_geocoded(session, geocoded_ids, reference=reference)
    return {"geocoded": len(geocoded_ids), "in_sp": in_sp, "out_sp": out_sp,
            "zero_results": zero, **dd}


def main() -> None:
    from .config import GOOGLE_MAPS_API_KEY

    if not GOOGLE_MAPS_API_KEY:
        print("ERRO: defina GOOGLE_MAPS_API_KEY (Geocoding API + billing no Google Cloud)")
        sys.exit(1)

    import truststore
    truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

    from .db import SessionLocal
    from .ingestion.geocoder import GoogleGeocoder

    today = datetime.now(_SP_TZ).date()
    with SessionLocal() as session:
        out = geocode_all(session, GoogleGeocoder(GOOGLE_MAPS_API_KEY), reference=today)
        session.commit()
        print(f"geocoded={out['geocoded']} (in_sp={out['in_sp']} out_sp={out['out_sp']} "
              f"zero_results={out['zero_results']}) | merged={out['merged']} "
              f"review={out['review']} distinct={out['distinct']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_geocode_venues.py -v`
Expected: PASS (5 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/geocode_venues.py tests/test_geocode_venues.py
git commit -m "feat: runner geocode_venues (backfill + re-dedup + relatorio in/out SP)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 9: adicionar `geocode_venues` ao daily

**Files:**
- Modify: `src/nightlife/daily.py:51-56` (lista `STEPS`)
- Test: `tests/test_daily_steps.py`

Contexto: o geocoding roda **depois** do `ingest_ra` (que traz venues novos sem geo) e antes seria indiferente ao IG/flyers, mas colocá-lo logo após o RA garante que os venues recém-ingeridos já saiam geocodados no mesmo run.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_daily_steps.py
from nightlife.daily import STEPS


def test_geocode_venues_roda_depois_do_ra():
    names = [name for name, _ in STEPS]
    assert "geocode_venues" in names
    assert names.index("geocode_venues") > names.index("ingest_ra")


def test_geocode_step_invoca_o_modulo_certo():
    argv = dict(STEPS)["geocode_venues"]
    assert argv[-2:] == ["-m", "nightlife.geocode_venues"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_daily_steps.py -v`
Expected: FAIL com `assert 'geocode_venues' in [...]`

- [ ] **Step 3: Write minimal implementation**

Modificar a lista `STEPS` em `src/nightlife/daily.py` (inserir após `ingest_ra`):

```python
STEPS: list[tuple[str, list[str]]] = [
    ("discover_handles", [sys.executable, "-m", "nightlife.discover_handles"]),
    ("ingest_ra", [sys.executable, "-m", "nightlife.ingest_ra"]),
    ("geocode_venues", [sys.executable, "-m", "nightlife.geocode_venues"]),
    ("ingest_ig", [sys.executable, "-m", "nightlife.ingest_ig"]),
    ("ingest_flyers", [sys.executable, "-m", "nightlife.ingest_flyers"]),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_daily_steps.py -v`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/daily.py tests/test_daily_steps.py
git commit -m "feat: geocode_venues entra nas STEPS do daily (apos ingest_ra)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 10: suíte completa + smoke real

**Files:** nenhum novo (verificação).

- [ ] **Step 1: Rodar a suíte inteira**

Run: `.venv/Scripts/python -m pytest -q`
Expected: todos verdes (os ~166 anteriores + os novos deste plano). Se o contador divergir, confira via exit code (`echo $?` = 0), não pelo texto (o pipe `\r` do Windows distorce a contagem).

- [ ] **Step 2: Aplicar a migration no banco real**

Run: `.venv/Scripts/python -m alembic upgrade head`
Expected: cria a tabela `geocode_cache` (revision `c3d4e5f6a7b8`).
Se falhar porque a tabela `alembic_version` não existe (banco criado via `create_all` e não migrado): rode `.venv/Scripts/python -m alembic stamp a1b2c3d4e5f6` (marca o estado atual) e então `upgrade head` de novo. Se a tabela `geocode_cache` já existir de outra forma, `stamp head` resolve.

- [ ] **Step 3: Smoke real do backfill (precisa da chave)**

Pré-requisito: o usuário define `GOOGLE_MAPS_API_KEY` no ambiente (Geocoding API + billing ativos no Google Cloud). Sem a chave, pular este passo e reportar ao usuário.

Run: `.venv/Scripts/python -m nightlife.geocode_venues`
Expected: imprime `geocoded=~600 (in_sp=... out_sp=...) merged=... review=... distinct=...`. Confirmar no banco: `SELECT count(*) FROM venues WHERE lat IS NOT NULL` subiu de 220 para ~800; um dup conhecido (ex. "Mundo Pensante") virou 1 venue.

- [ ] **Step 4: Confirmar idempotência**

Run: `.venv/Scripts/python -m nightlife.geocode_venues` (segunda vez)
Expected: `geocoded=0` (todo mundo já tem geo) e nenhuma chamada nova à Google (cache). `merged=0`.

- [ ] **Step 5: Commit (se algum ajuste de smoke foi necessário)**

Se nada mudou no código, não há commit. Caso ajustes tenham sido feitos:

```bash
git add -A
git commit -m "chore: ajustes do smoke real de geocoding

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

## Notas de implementação

- **Zero rede nos testes:** todo teste injeta um geocoder fake ou faz monkeypatch em `httpx.get`. Nenhum teste toca a Google.
- **Ordem de merge (idempotência):** `rededup_geocoded` só processa cada id uma vez e pula os que já foram fundidos (`merged_away`). O `merge_venues` faz `flush` antes e depois do `delete` para o `recompute` enxergar a evidência movida.
- **`match_venue` com `threshold=0.0`:** queremos sempre o melhor candidato; a decisão vem de `classify_venue_match` com a distância (mesmo padrão do `upsert_venue`).
- **Cache negativo:** `ZERO_RESULTS` é gravado para não re-cobrar endereços impossíveis todo dia; `ERROR` (quota/rede) nunca é gravado, para tentar de novo no próximo run.
