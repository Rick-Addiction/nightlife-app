# Ciclo A — Identidade & Vivacidade dos Venues — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O mapa mostrar só venues com sinal de vida, com nome atual e site oficial, automaticamente — no caso-teste: Selva renomeada, Inferno fundido nela, Beco 203 fundido no Kat Klub, zero intervenção manual.

**Architecture:** Três camadas: (1) `PlacesClient` ganha `languageCode: pt-BR` (nomes atuais), `businessStatus` no Nearby e um método `place_details` (nome canônico + status + site); (2) runner novo `enrich_places` = enriquecimento por place_id (cache 30d) + reconciliação em duas regras (consolidação por nome ≥0.70/≤30m/verificado; supersessão de fantasmas só-RA/OSM); (3) `venue_relevance` v2 — pin só corroborado-ou-ativo. `PlacesSource` ganha subdivisão automática ao saturar + 6 sementes novas. Zero mudança no frontend.

**Tech Stack:** Python 3.14, SQLAlchemy 2.0, httpx + truststore, Alembic, pytest, Postgres (porta 5434). Places API (New): `places:searchNearby` + `GET /v1/places/{id}`.

**Referências do código existente (assinaturas verificadas):**
- `nightlife.persistence.venue_merge`: `merge_venues(session, survivor: Venue, loser: Venue, *, reference: date) -> Venue` (move VenueSources/Events, grava VerificationLog do merge, deleta loser); `_pick_survivor(a, b) -> (survivor, loser)` (maior confiança, empate → menor id).
- `nightlife.domain.matching`: `name_similarity(a, b) -> float`; `_haversine_km(lat1, lng1, lat2, lng2) -> float`.
- `nightlife.models`: `Venue(id, name, category, lat, lng, address, instagram, website, status, confidence, is_monitored, ...)`, `VenueSource(venue_id, source_type, source_url, last_seen_at, ...)`, `Event(venue_id, ...)`, `DedupeCandidate(kind, a_id, b_id, similarity_score, decision)`, `VerificationLog(entity_type, entity_id, note)`.
- `nightlife.domain.nightlife_relevance.venue_relevance(name, category, has_events, is_monitored)` — callers: `api/main.py:58` e `persistence/ig_state.py:23`.
- Última migration: `c3d4e5f6a7b8` (geocode_cache). Testes: fixture `session` (conftest, rollback por teste; schema via `create_all`).
- Runner pattern: ver `src/nightlife/enrich_places`-análogos `geocode_venues.py`/`discover_places.py` (key guard → truststore → SessionLocal → commit → print → exit 1 em erro).

**Convenção de commit:** trailer `Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu`.

**Testes:** `.venv/Scripts/python -m pytest <arquivo> -v` (Postgres 5434 de pé). Suíte completa com `--basetemp="<scratchpad>/bt"` (o temp default do pytest está travado nesta máquina).

---

### Task 1: `PlacesClient` — languageCode pt-BR + businessStatus no Nearby

**Files:**
- Modify: `src/nightlife/ingestion/places_client.py`
- Test: `tests/test_places_client.py` (adicionar testes; os existentes continuam passando)

- [ ] **Step 1: Write the failing tests**

Adicionar ao FIM de `tests/test_places_client.py` (o arquivo já tem `_fake_response`, `_FakeClient`, `_client`):

```python
class _RecordingClient:
    """Captura o body enviado, devolve payload fixo."""
    def __init__(self, payload):
        self.payload = payload
        self.last_json = None

    def post(self, url, headers=None, json=None):
        self.last_json = json
        return _fake_response(self.payload)


def test_nearby_manda_language_code_pt_br():
    rec = _RecordingClient({"places": []})
    PlacesClient("KEY", client=rec).search_nearby(-23.5, -46.6, 1000, "night_club")
    assert rec.last_json["languageCode"] == "pt-BR"


def test_nearby_parseia_business_status():
    payload = {"places": [
        {"id": "PID1", "displayName": {"text": "Selva Club"},
         "location": {"latitude": -23.55, "longitude": -46.65},
         "primaryType": "night_club", "businessStatus": "OPERATIONAL"},
    ]}
    res = _client(payload).search_nearby(-23.55, -46.65, 1000, "night_club")
    assert res[0].business_status == "OPERATIONAL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_places_client.py -v -k "language_code or business_status"`
Expected: FAIL (`KeyError: 'languageCode'` / `AttributeError: ... business_status`)

- [ ] **Step 3: Write minimal implementation**

Em `src/nightlife/ingestion/places_client.py`:

1. `_FIELD_MASK` vira:
```python
_FIELD_MASK = ("places.id,places.displayName,places.location,"
               "places.formattedAddress,places.primaryType,places.businessStatus")
```
2. `PlaceResult` ganha o campo (com default, pra não quebrar construções existentes):
```python
@dataclass(frozen=True)
class PlaceResult:
    place_id: str
    name: str
    lat: float
    lng: float
    address: str | None
    primary_type: str | None
    business_status: str | None = None
```
3. No `body` do `search_nearby`, adicionar a linha (depois de `"rankPreference"`):
```python
            "languageCode": "pt-BR",
```
Comentário na linha: `# sem isso a API serve o indice EN com alias VELHO (caso Selva/Inferno)`.
4. No `out.append(PlaceResult(...))`, adicionar:
```python
                business_status=p.get("businessStatus"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_places_client.py -v`
Expected: PASS (8 testes — 6 existentes + 2 novos)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/ingestion/places_client.py tests/test_places_client.py
git commit -m "feat: languageCode pt-BR + businessStatus no Nearby (caso Selva)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 2: `PlacesClient.place_details` + `PlaceDetails`

**Files:**
- Modify: `src/nightlife/ingestion/places_client.py`
- Test: `tests/test_places_client.py` (adicionar)

- [ ] **Step 1: Write the failing tests**

Adicionar ao fim de `tests/test_places_client.py`:

```python
from nightlife.ingestion.places_client import PlaceDetails


class _FakeGetClient:
    """Client com .get pro Details; devolve payload fixo (ou levanta)."""
    def __init__(self, payload=None, raises=None):
        self.payload = payload
        self.raises = raises
        self.last_params = None

    def get(self, url, headers=None, params=None):
        self.last_params = params
        if self.raises is not None:
            raise self.raises
        return _fake_response(self.payload)


def test_place_details_parseia_nome_status_site():
    payload = {"id": "PID1", "displayName": {"text": "Selva Club", "languageCode": "pt"},
               "businessStatus": "OPERATIONAL", "websiteUri": "https://selva.club/"}
    fake = _FakeGetClient(payload)
    det = PlacesClient("KEY", client=fake).place_details("PID1")
    assert det == PlaceDetails(name="Selva Club", business_status="OPERATIONAL",
                               website="https://selva.club/")
    assert fake.last_params["languageCode"] == "pt-BR"


def test_place_details_sem_nome_vira_none():
    det = PlacesClient("KEY", client=_FakeGetClient({"id": "PID1"})).place_details("PID1")
    assert det is None


def test_place_details_erro_vira_none():
    det = PlacesClient("KEY", client=_FakeGetClient(raises=httpx.ConnectError("x"))).place_details("PID1")
    assert det is None


def test_place_details_campos_opcionais_ausentes():
    det = PlacesClient("KEY", client=_FakeGetClient({"displayName": {"text": "X"}})).place_details("PID1")
    assert det == PlaceDetails(name="X", business_status=None, website=None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_places_client.py -v -k place_details`
Expected: FAIL com `ImportError: cannot import name 'PlaceDetails'`

- [ ] **Step 3: Write minimal implementation**

Em `places_client.py`, adicionar após `PlaceResult`:

```python
_DETAILS_ENDPOINT = "https://places.googleapis.com/v1/places/{place_id}"
_DETAILS_FIELD_MASK = "id,displayName,businessStatus,websiteUri"


@dataclass(frozen=True)
class PlaceDetails:
    name: str
    business_status: str | None
    website: str | None
```

E o método na classe `PlacesClient`:

```python
    def place_details(self, place_id: str) -> PlaceDetails | None:
        """Nome canonico pt-BR + businessStatus + site oficial de um place_id.
        None = erro retentavel (o chamador NAO deve gravar enriched_at)."""
        headers = {"X-Goog-Api-Key": self._key, "X-Goog-FieldMask": _DETAILS_FIELD_MASK}
        try:
            resp = self._client.get(_DETAILS_ENDPOINT.format(place_id=place_id),
                                    headers=headers, params={"languageCode": "pt-BR"})
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        name = (data.get("displayName") or {}).get("text")
        if not name:
            return None  # sem nome nao ha o que enriquecer
        return PlaceDetails(name=name, business_status=data.get("businessStatus"),
                            website=data.get("websiteUri"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_places_client.py -v`
Expected: PASS (12 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/ingestion/places_client.py tests/test_places_client.py
git commit -m "feat: PlacesClient.place_details (nome canonico + status + site)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 3: `PlacesSource` — subdivisão automática + filtro CLOSED_PERMANENTLY + 6 sementes

**Files:**
- Modify: `src/nightlife/ingestion/places_source.py`
- Test: `tests/test_places_source.py` (adicionar + atualizar 1)

- [ ] **Step 1: Write the failing tests**

Adicionar ao fim de `tests/test_places_source.py`:

```python
class _SaturatingClient:
    """1a chamada devolve 20 (satura); as seguintes devolvem vazio."""
    def __init__(self, lots):
        self.lots = lots
        self.calls = []

    def search_nearby(self, lat, lng, radius, included_type):
        self.calls.append((lat, lng, radius, included_type))
        return list(self.lots) if len(self.calls) == 1 else []


def test_saturacao_subdivide_em_4_subcelulas():
    lots = [PlaceResult(place_id=f"P{i}", name=f"Club {i}", lat=-23.5, lng=-46.6,
                        address=None, primary_type="night_club") for i in range(20)]
    client = _SaturatingClient(lots)
    src = PlacesSource(client, seeds=[("Augusta", -23.5545, -46.6620)],
                       types=("night_club",), radius=1000, log=lambda m: None)
    vs = list(src.venues())
    assert len(vs) == 20                     # os 20 da celula saturada SAO emitidos
    assert len(client.calls) == 5            # 1 original + 4 sub-celulas
    for _lat, _lng, r, _t in client.calls[1:]:
        assert abs(r - 720) < 1              # sub-raio = 1000 * 0.72


def test_subdivisao_respeita_freio_de_raio():
    lots = [PlaceResult(place_id=f"P{i}", name=f"C{i}", lat=-23.5, lng=-46.6,
                        address=None, primary_type="night_club") for i in range(20)]
    client = _SaturatingClient(lots)
    # raio 180: sub-raio seria 129.6 < 150 -> NAO subdivide
    src = PlacesSource(client, seeds=[("X", -23.5, -46.6)], types=("night_club",),
                       radius=180, log=lambda m: None)
    list(src.venues())
    assert len(client.calls) == 1


def test_closed_permanently_descartado_na_descoberta():
    morto = PlaceResult(place_id="PDEAD", name="Fechado", lat=-23.5, lng=-46.6,
                        address=None, primary_type="night_club",
                        business_status="CLOSED_PERMANENTLY")
    vivo = PlaceResult(place_id="PLIVE", name="Aberto", lat=-23.5, lng=-46.6,
                       address=None, primary_type="night_club",
                       business_status="OPERATIONAL")
    client = _FakePlacesClient(by_type={"night_club": [morto, vivo]})
    src = PlacesSource(client, seeds=[("X", -23.5, -46.6)], types=("night_club",))
    names = [v.name for v in src.venues()]
    assert names == ["Aberto"]
```

E ATUALIZAR `test_defaults_de_seeds_e_types_existem` para:

```python
def test_defaults_de_seeds_e_types_existem():
    assert len(SEED_POINTS) >= 20
    names = [n for n, _, _ in SEED_POINTS]
    assert "Baixa Augusta/Consolacao" in names   # o quarteirao da Selva
    assert "night_club" in SEARCH_TYPES and "event_venue" not in SEARCH_TYPES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_places_source.py -v`
Expected: FAIL (subdivisão inexistente → 1 chamada; CLOSED_PERMANENTLY não filtrado; sementes < 20)

- [ ] **Step 3: Write minimal implementation**

Em `places_source.py`: adicionar `import math` no topo; adicionar as sementes ao fim de `SEED_POINTS`:

```python
    ("Baixa Augusta/Consolacao", -23.5515, -46.6505),
    ("Liberdade",          -23.5590, -46.6350),
    ("Santa Cecilia",      -23.5405, -46.6535),
    ("Bom Retiro",         -23.5270, -46.6430),
    ("Mooca",              -23.5555, -46.5985),
    ("Ipiranga",           -23.5920, -46.6100),
```

Adicionar constantes após `_SEARCH_RADIUS_M`:

```python
# subdivisao ao saturar o teto de 20 do Nearby: 4 sub-celulas cobrem o circulo
# original (centros +-r/2, sub-raio 0.72r ~ 1/sqrt(2) com folga); freios de
# raio minimo e profundidade limitam o custo. Sobreposicao e inocua (dedup por
# place_id no pipeline).
_MIN_SUBDIVIDE_RADIUS_M = 150
_MAX_SUBDIVIDE_DEPTH = 3
```

Substituir o método `venues()` por:

```python
    def venues(self) -> Iterable[RawVenue]:
        for name, lat, lng in self._seeds:
            for t in self._types:
                yield from self._search_cell(name, lat, lng, self._radius, t, 0)

    def _search_cell(self, name: str, lat: float, lng: float, radius: float,
                     t: str, depth: int) -> Iterable[RawVenue]:
        results = self._client.search_nearby(lat, lng, radius, t)
        for r in results:
            if r.business_status == "CLOSED_PERMANENTLY":
                continue  # morto confirmado pelo Google: nem cria venue
            yield RawVenue(
                name=r.name, source_type="google_places",
                lat=r.lat, lng=r.lng, address=r.address,
                category=_category_for(r.primary_type), source_url=r.place_id,
            )
        if len(results) < 20:
            return
        sub_r = radius * 0.72
        if sub_r < _MIN_SUBDIVIDE_RADIUS_M or depth >= _MAX_SUBDIVIDE_DEPTH:
            self._log(f"[places] saturou 20 em {name!r}/{t} r={radius:.0f}m (freio: nao subdivide)")
            return
        self._log(f"[places] saturou 20 em {name!r}/{t} r={radius:.0f}m -> subdividindo")
        dlat = (radius / 2) / 111320.0
        dlng = (radius / 2) / (111320.0 * math.cos(math.radians(lat)))
        for sy, sx in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            yield from self._search_cell(name, lat + sy * dlat, lng + sx * dlng,
                                         sub_r, t, depth + 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_places_source.py -v`
Expected: PASS (8 testes). Nota: `test_venues_loga_saturacao_em_20` (existente) continua verde — o fake devolve 20 sempre, a recursão para no freio de profundidade e o log "satur" aparece.

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/ingestion/places_source.py tests/test_places_source.py
git commit -m "feat: subdivisao automatica ao saturar + filtro CLOSED_PERMANENTLY + 6 sementes

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 4: model + migration — `business_status` e `enriched_at`

**Files:**
- Modify: `src/nightlife/models.py` (classe `Venue`)
- Create: `migrations/versions/d4e5f6a7b8c9_venue_business_status.py`
- Test: `tests/test_venue_business_status_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_venue_business_status_model.py
from datetime import datetime, timezone

from nightlife.models import Venue


def test_venue_persiste_business_status_e_enriched_at(session):
    now = datetime.now(timezone.utc)
    v = Venue(name="Selva Club", business_status="OPERATIONAL", enriched_at=now)
    session.add(v)
    session.flush()
    got = session.get(Venue, v.id)
    assert got.business_status == "OPERATIONAL"
    assert got.enriched_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_venue_business_status_model.py -v`
Expected: FAIL com `TypeError: 'business_status' is an invalid keyword argument`

- [ ] **Step 3: Write minimal implementation**

Em `models.py`, classe `Venue`, adicionar após `status`:

```python
    business_status: Mapped[str | None] = mapped_column(String(30), default=None)  # do Places Details
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
```

Criar `migrations/versions/d4e5f6a7b8c9_venue_business_status.py`:

```python
"""venues: business_status + enriched_at (enrichment do Places)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('venues', sa.Column('business_status', sa.String(length=30), nullable=True))
    op.add_column('venues', sa.Column('enriched_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('venues', 'enriched_at')
    op.drop_column('venues', 'business_status')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_venue_business_status_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/models.py migrations/versions/d4e5f6a7b8c9_venue_business_status.py tests/test_venue_business_status_model.py
git commit -m "feat: colunas business_status/enriched_at no Venue + migration

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 5: `enrich_places.enrich_all` (+ `main` parcial)

**Files:**
- Create: `src/nightlife/enrich_places.py`
- Test: `tests/test_enrich_places.py`

Contexto: `enrich_all(session, client, *, now, max_age_days=30)` recebe o client injetado (testes usam fake — zero rede). A reconciliação entra na Task 6 no mesmo arquivo.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_enrich_places.py
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from nightlife.models import Venue, VenueSource, VerificationLog
from nightlife.ingestion.places_client import PlaceDetails
from nightlife.enrich_places import enrich_all

NOW = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)


class FakeDetailsClient:
    """place_details por place_id; conta chamadas."""
    def __init__(self, table):
        self.table = table          # place_id -> PlaceDetails | None
        self.calls = 0

    def place_details(self, place_id):
        self.calls += 1
        return self.table.get(place_id)


def _gp_venue(session, name, pid, **kw):
    v = Venue(name=name, lat=-23.5, lng=-46.6, category="nightclub", **kw)
    session.add(v)
    session.flush()
    session.add(VenueSource(venue_id=v.id, source_type="google_places", source_url=pid))
    session.flush()
    return v


def test_enrich_renomeia_com_trilha(session):
    v = _gp_venue(session, "Inferno Club", "PID_SELVA")
    client = FakeDetailsClient({"PID_SELVA": PlaceDetails(
        name="Selva Club", business_status="OPERATIONAL", website="https://selva.club/")})
    out = enrich_all(session, client, now=NOW)
    session.flush()
    assert v.name == "Selva Club"
    assert v.website == "https://selva.club/"
    assert v.business_status == "OPERATIONAL" and v.status == "operational"
    assert v.enriched_at == NOW
    assert out["renamed"] == 1 and out["enriched"] == 1
    logs = session.scalars(select(VerificationLog).where(
        VerificationLog.entity_id == v.id, VerificationLog.entity_type == "venue")).all()
    assert any("rename" in (lg.note or "") and "Selva Club" in lg.note for lg in logs)


def test_enrich_mapeia_closed_permanently(session):
    v = _gp_venue(session, "Morto Club", "PID_DEAD")
    client = FakeDetailsClient({"PID_DEAD": PlaceDetails(
        name="Morto Club", business_status="CLOSED_PERMANENTLY", website=None)})
    out = enrich_all(session, client, now=NOW)
    session.flush()
    assert v.status == "permanently_closed" and v.business_status == "CLOSED_PERMANENTLY"
    assert out["closed_perm"] == 1 and out["renamed"] == 0


def test_enrich_cache_30d_nao_rechama(session):
    v = _gp_venue(session, "Ja Enriquecido", "PID_X",
                  enriched_at=NOW - timedelta(days=5))
    client = FakeDetailsClient({"PID_X": PlaceDetails(name="Novo Nome", business_status=None, website=None)})
    out = enrich_all(session, client, now=NOW)
    assert client.calls == 0 and out["skipped_cached"] == 1
    assert v.name == "Ja Enriquecido"           # intocado


def test_enrich_erro_nao_grava_enriched_at(session):
    v = _gp_venue(session, "Erro Club", "PID_ERR")
    client = FakeDetailsClient({"PID_ERR": None})   # Details falhou (retentavel)
    out = enrich_all(session, client, now=NOW)
    assert out["errors"] == 1
    assert v.enriched_at is None                # retenta no proximo run


def test_enrich_ignora_venue_sem_place_id(session):
    v = Venue(name="So RA", lat=-23.5, lng=-46.6)
    session.add(v)
    session.flush()
    session.add(VenueSource(venue_id=v.id, source_type="ra", source_url="https://ra.co/clubs/1"))
    session.flush()
    client = FakeDetailsClient({})
    enrich_all(session, client, now=NOW)
    assert client.calls == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_enrich_places.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'nightlife.enrich_places'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/nightlife/enrich_places.py
"""Enriquecimento de venues via Place Details + reconciliacao (Ciclo A).

Details por place_id: nome canonico pt-BR (renomeia com trilha), businessStatus
(mata fechados), websiteUri (site oficial -> elo do Ciclo B). Cache de 30 dias
via enriched_at. Sob demanda: python -m nightlife.enrich_places
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Venue, VenueSource, VerificationLog

_STATUS_MAP = {
    "OPERATIONAL": "operational",
    "CLOSED_TEMPORARILY": "closed",
    "CLOSED_PERMANENTLY": "permanently_closed",
}


def _place_ids_by_venue(session: Session) -> dict[int, str]:
    """place_id (source_url) mais recente por venue com evidencia google_places."""
    rows = session.execute(
        select(VenueSource.venue_id, VenueSource.source_url)
        .where(VenueSource.source_type == "google_places",
               VenueSource.source_url.is_not(None))
        .order_by(VenueSource.venue_id, VenueSource.last_seen_at.desc())
    ).all()
    out: dict[int, str] = {}
    for vid, url in rows:
        out.setdefault(vid, url)    # primeiro = last_seen mais recente
    return out


def enrich_all(session: Session, client, *, now: datetime, max_age_days: int = 30) -> dict:
    out = {"enriched": 0, "renamed": 0, "websites_set": 0, "closed_perm": 0,
           "closed_temp": 0, "skipped_cached": 0, "errors": 0}
    cutoff = now - timedelta(days=max_age_days)
    for vid, pid in _place_ids_by_venue(session).items():
        venue = session.get(Venue, vid)
        if venue is None:
            continue
        if venue.enriched_at is not None and venue.enriched_at >= cutoff:
            out["skipped_cached"] += 1
            continue
        det = client.place_details(pid)
        if det is None:
            out["errors"] += 1      # retentavel: NAO grava enriched_at
            continue
        if det.name and det.name != venue.name:
            session.add(VerificationLog(
                entity_type="venue", entity_id=venue.id,
                note=f"rename: {venue.name!r} -> {det.name!r} (places)"))
            venue.name = det.name
            out["renamed"] += 1
        if det.website and det.website != venue.website:
            venue.website = det.website
            out["websites_set"] += 1
        venue.business_status = det.business_status
        mapped = _STATUS_MAP.get(det.business_status or "")
        if mapped:
            venue.status = mapped
        if det.business_status == "CLOSED_PERMANENTLY":
            out["closed_perm"] += 1
        elif det.business_status == "CLOSED_TEMPORARILY":
            out["closed_temp"] += 1
        venue.enriched_at = now
        out["enriched"] += 1
    session.flush()
    return out


def main() -> None:
    from .config import GOOGLE_MAPS_API_KEY

    if not GOOGLE_MAPS_API_KEY:
        print("ERRO: defina GOOGLE_MAPS_API_KEY (Places API New + billing)")
        sys.exit(1)

    import truststore
    truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

    from .db import SessionLocal
    from .ingestion.places_client import PlacesClient

    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        client = PlacesClient(GOOGLE_MAPS_API_KEY)
        out = enrich_all(session, client, now=now)
        session.commit()
        print("enrich:", out)


if __name__ == "__main__":
    main()
```

(`date` do import é usado na Task 6 pelo `reconcile_venues`; mantenha.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_enrich_places.py -v`
Expected: PASS (5 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/enrich_places.py tests/test_enrich_places.py
git commit -m "feat: enrich_places (Details -> nome canonico/status/site, cache 30d)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 6: `reconcile_venues` — consolidação + supersessão

**Files:**
- Modify: `src/nightlife/enrich_places.py` (adicionar função + fiar no `main`)
- Test: `tests/test_reconcile.py`

Contexto: duas regras, nesta ordem. Regra 1 (consolidação): par ≤30m + **score ≥ 0.70, onde score = `name_similarity` + boost geo de 0.1** (a MESMA semântica do `match_venue` para pares próximos — todo par do gate está ≤30m; sem o boost, o caso-motivador "Kat Klub São Paulo" vs "Kat Klub" dá 0.615 cru e não fundiria) + ≥1 lado verificado (evidência google_places E `business_status != CLOSED_PERMANENTLY`) → merge com `_pick_survivor`. Regra 2 (supersessão): fantasma (exatamente 1 fonte ∈ {ra, osm}, 0 eventos, geo) + exatamente 1 verificado ≤30m → merge no verificado; 2+ candidatos ≤30m OU (0 ≤30m e ≥1 ≤60m) → DedupeCandidate review.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reconcile.py
from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue, VenueSource, Event, DedupeCandidate
from nightlife.enrich_places import reconcile_venues

REF = date(2026, 7, 9)


def _venue(session, name, lat, lng, sources=(), confidence=0, with_event=False):
    v = Venue(name=name, lat=lat, lng=lng, category="nightclub", confidence=confidence)
    session.add(v)
    session.flush()
    for stype, url in sources:
        session.add(VenueSource(venue_id=v.id, source_type=stype, source_url=url))
    if with_event:
        session.add(Event(name=f"Festa em {name}", venue_id=v.id))
    session.flush()
    return v


def test_consolidacao_funde_par_verificado_similar(session):
    # caso Kat Klub: RA "Kat Klub Sao Paulo" + Places "Kat Klub" a ~15m, sim ~0.72
    ra = _venue(session, "Kat Klub Sao Paulo", -23.55202, -46.65170,
                sources=[("ra", "https://ra.co/clubs/2")], confidence=40)
    gp = _venue(session, "Kat Klub", -23.55210, -46.65175,
                sources=[("google_places", "PID_KAT")], confidence=30)
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["consolidated"] == 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    survivor = session.scalars(select(Venue)).one()
    srcs = {s.source_type for s in session.scalars(select(VenueSource))}
    assert srcs == {"ra", "google_places"}     # evidencias unificadas
    assert survivor.id == ra.id                # _pick_survivor: maior confianca


def test_consolidacao_ignora_par_sem_lado_verificado(session):
    _venue(session, "Bar Alfa", -23.55, -46.65, sources=[("ra", "u1")])
    _venue(session, "Bar Alfa", -23.5501, -46.6501, sources=[("osm", "u2")])
    out = reconcile_venues(session, reference=REF)
    assert out["consolidated"] == 0
    assert session.scalar(select(func.count()).select_from(Venue)) == 2


def test_supersessao_funde_fantasma_ra_no_verificado(session):
    # caso Inferno->Selva: nomes DIFERENTES (sim < 0.70), <=30m, fantasma so-RA
    selva = _venue(session, "Selva Club", -23.55157, -46.65077,
                   sources=[("google_places", "PID_SELVA")], confidence=30)
    inferno = _venue(session, "Inferno Club", -23.55170, -46.65072,
                     sources=[("ra", "https://ra.co/clubs/28883")], confidence=0)
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["superseded"] == 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    survivor = session.scalars(select(Venue)).one()
    assert survivor.name == "Selva Club"
    urls = {s.source_url for s in session.scalars(select(VenueSource))}
    assert "https://ra.co/clubs/28883" in urls   # identidade RA migrou


def test_supersessao_funde_fantasma_osm(session):
    # caso Beco 203 -> Kat Klub (fantasma so-OSM)
    kat = _venue(session, "Kat Klub", -23.55202, -46.65170,
                 sources=[("google_places", "PID_KAT")], confidence=30)
    _venue(session, "Beco 203", -23.55215, -46.65180,
           sources=[("osm", "https://osm.org/node/1")], confidence=20)
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["superseded"] == 1
    assert session.scalars(select(Venue)).one().name == "Kat Klub"


def test_supersessao_dois_candidatos_vira_review(session):
    # nomes DISSIMILARES de proposito: senao a regra 1 (consolidacao) fundiria
    # os dois verificados antes da regra 2 rodar
    _venue(session, "Selva Club", -23.55000, -46.65000,
           sources=[("google_places", "PA")], confidence=30)
    _venue(session, "Outs Club", -23.55010, -46.65010,
           sources=[("google_places", "PB")], confidence=30)
    _venue(session, "Fantasma", -23.55005, -46.65005,
           sources=[("ra", "u")], confidence=0)
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["superseded"] == 0 and out["review_queued"] == 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 3
    assert session.scalar(select(func.count()).select_from(DedupeCandidate)) == 1


def test_supersessao_30_a_60m_vira_review(session):
    _venue(session, "Verificado", -23.55000, -46.65000,
           sources=[("google_places", "P1")], confidence=30)
    # ~44m ao sul (0.0004 graus de lat)
    _venue(session, "Fantasma Longe", -23.55040, -46.65000,
           sources=[("ra", "u")], confidence=0)
    out = reconcile_venues(session, reference=REF)
    assert out["superseded"] == 0 and out["review_queued"] == 1


def test_fantasma_com_evento_e_intocado(session):
    _venue(session, "Verificado", -23.55000, -46.65000,
           sources=[("google_places", "P1")], confidence=30)
    _venue(session, "Com Evento", -23.55005, -46.65005,
           sources=[("ra", "u")], confidence=0, with_event=True)
    out = reconcile_venues(session, reference=REF)
    assert out["superseded"] == 0 and out["review_queued"] == 0
    assert session.scalar(select(func.count()).select_from(Venue)) == 2


def test_reconcile_e_idempotente(session):
    _venue(session, "Selva Club", -23.55157, -46.65077,
           sources=[("google_places", "PID_SELVA")], confidence=30)
    _venue(session, "Inferno Club", -23.55170, -46.65072,
           sources=[("ra", "u")], confidence=0)
    reconcile_venues(session, reference=REF)
    session.flush()
    out2 = reconcile_venues(session, reference=REF)
    assert out2["superseded"] == 0 and out2["consolidated"] == 0
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_reconcile.py -v`
Expected: FAIL com `ImportError: cannot import name 'reconcile_venues'`

- [ ] **Step 3: Write minimal implementation**

Adicionar em `enrich_places.py` (imports novos no topo do arquivo):

```python
from sqlalchemy import distinct, or_

from .domain.matching import _haversine_km, name_similarity
from .models import DedupeCandidate, Event
from .persistence.venue_merge import _pick_survivor, merge_venues
```

E a função:

```python
def _sources_by_venue(session: Session) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for vid, stype in session.execute(select(VenueSource.venue_id, VenueSource.source_type)):
        out.setdefault(vid, set()).add(stype)
    return out


def reconcile_venues(session: Session, *, reference: date) -> dict:
    """Duas regras, nesta ordem. 1) Consolidacao: par <=30m com nome >=0.70 e
    >=1 lado verificado -> merge (mata pins duplicados tipo 'Kat Klub' vs
    'Kat Klub Sao Paulo'). 2) Supersessao: fantasma (1 fonte ra/osm, 0 eventos)
    com exatamente 1 verificado <=30m -> funde nele (Inferno->Selva, Beco->Kat);
    ambiguidade -> fila de review. Merges via merge_venues (auditavel)."""
    out = {"consolidated": 0, "superseded": 0, "review_queued": 0, "untouched": 0}

    def _snapshot():
        srcs = _sources_by_venue(session)
        with_ev = set(session.scalars(
            select(distinct(Event.venue_id)).where(Event.venue_id.is_not(None))))
        venues = session.scalars(select(Venue).where(Venue.lat.is_not(None))).all()
        return venues, srcs, with_ev

    def _verified(v: Venue, srcs: dict[int, set[str]]) -> bool:
        return ("google_places" in srcs.get(v.id, set())
                and v.business_status != "CLOSED_PERMANENTLY")

    def _dist_km(a: Venue, b: Venue) -> float:
        return _haversine_km(a.lat, a.lng, b.lat, b.lng)

    # regra 1: consolidacao por nome
    venues, srcs, _ = _snapshot()
    gone: set[int] = set()
    for i, a in enumerate(venues):
        if a.id in gone:
            continue
        for b in venues[i + 1:]:
            if b.id in gone or a.id in gone:
                continue
            if not (_verified(a, srcs) or _verified(b, srcs)):
                continue
            if _dist_km(a, b) > 0.03:
                continue
            # score com o MESMO boost geo do match_venue (par <=30m): sem ele,
            # "Kat Klub Sao Paulo" vs "Kat Klub" da 0.615 cru e nao consolidaria
            if min(1.0, name_similarity(a.name, b.name) + 0.1) < 0.70:
                continue
            survivor, loser = _pick_survivor(a, b)
            merge_venues(session, survivor, loser, reference=reference)
            gone.add(loser.id)
            out["consolidated"] += 1

    # regra 2: supersessao de fantasmas (snapshot fresco: regra 1 mudou o banco)
    venues, srcs, with_ev = _snapshot()
    gone = set()
    for g in venues:
        if g.id in gone:
            continue
        gsrc = srcs.get(g.id, set())
        if not (len(gsrc) == 1 and next(iter(gsrc)) in ("ra", "osm")):
            continue
        if g.id in with_ev:
            continue                      # tem evento: nao e fantasma
        near30 = [v for v in venues
                  if v.id != g.id and v.id not in gone
                  and _verified(v, srcs) and _dist_km(g, v) <= 0.03]
        if len(near30) == 1:
            merge_venues(session, near30[0], g, reference=reference)
            gone.add(g.id)
            out["superseded"] += 1
            continue
        near60 = [v for v in venues
                  if v.id != g.id and v.id not in gone
                  and _verified(v, srcs) and _dist_km(g, v) <= 0.06]
        if len(near30) >= 2 or near60:
            other = (near30 or near60)[0]
            exists = session.scalars(select(DedupeCandidate).where(
                DedupeCandidate.kind == "venue",
                or_((DedupeCandidate.a_id == g.id) & (DedupeCandidate.b_id == other.id),
                    (DedupeCandidate.a_id == other.id) & (DedupeCandidate.b_id == g.id)),
            )).first()
            if exists is None:
                session.add(DedupeCandidate(
                    kind="venue", a_id=g.id, b_id=other.id,
                    similarity_score=name_similarity(g.name, other.name),
                    decision="review"))
            out["review_queued"] += 1
        else:
            out["untouched"] += 1

    session.flush()
    return out
```

E no `main()`, após o `enrich_all` (antes do `session.commit()`):

```python
        rec = reconcile_venues(session, reference=now.date())
        session.commit()
        print("enrich:", out)
        print("reconcile:", rec)
```
(Remover o `session.commit()`/`print` antigos para não duplicar.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_reconcile.py tests/test_enrich_places.py -v`
Expected: PASS (13 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/enrich_places.py tests/test_reconcile.py
git commit -m "feat: reconcile_venues (consolidacao por nome + supersessao de fantasmas)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 7: `venue_relevance` v2 + caller `ig_state`

**Files:**
- Modify: `src/nightlife/domain/nightlife_relevance.py`
- Modify: `src/nightlife/persistence/ig_state.py:21-24`
- Test: `tests/test_nightlife_relevance.py` (REESCREVER `test_venue_relevance`)

- [ ] **Step 1: Write the failing tests**

Em `tests/test_nightlife_relevance.py`, SUBSTITUIR a função `test_venue_relevance` por:

```python
def test_venue_relevance_v2():
    # blocked tem precedencia sobre tudo
    assert venue_relevance("Buffet X", "nightclub", True, True) == "blocked"
    assert venue_relevance("Selva Club", "nightclub", True, True,
                           business_status="CLOSED_PERMANENTLY") == "blocked"
    # atividade vence sempre (qualquer categoria)
    assert venue_relevance("Espaco Y", "events_venue", True, False) == "relevant"
    assert venue_relevance("Espaco Z", "events_venue", False, True) == "relevant"
    # nightclub precisa estar VIVO: so-categoria nao basta mais (fantasmas do RA)
    assert venue_relevance("Lab Club", "nightclub", False, False) == "dormant"
    assert venue_relevance("Lab Club", "nightclub", False, False,
                           places_verified=True) == "relevant"
    assert venue_relevance("Lab Club", "nightclub", False, False,
                           source_count=2) == "relevant"
    assert venue_relevance("Lab Club", "nightclub", False, False,
                           has_contact=True) == "relevant"
    # nao-nightclub vivo mas sem evento continua dormant (bar verificado nao pina)
    assert venue_relevance("Bar Vivo", "bar", False, False,
                           places_verified=True) == "dormant"
    assert venue_relevance("Sem Cat", None, False, False) == "dormant"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_nightlife_relevance.py -v`
Expected: FAIL com `TypeError: venue_relevance() got an unexpected keyword argument`

- [ ] **Step 3: Write minimal implementation**

Em `nightlife_relevance.py`, substituir `venue_relevance` por:

```python
def venue_relevance(name: str | None, category: str | None,
                    has_events: bool, is_monitored: bool, *,
                    places_verified: bool = False,
                    business_status: str | None = None,
                    source_count: int = 1,
                    has_contact: bool = False) -> str:
    """'blocked' | 'relevant' | 'dormant'. v2 (Ciclo A): nightclub so e relevant
    se VIVO (verificado pelo Places, 2+ fontes ou contato) — o diretorio do RA
    guarda clubes historicos, entao categoria sozinha nao prova existencia.
    blocked (buffet, ou fechado em definitivo pelo Google) tem precedencia."""
    if is_buffet_name(name) or business_status == "CLOSED_PERMANENTLY":
        return "blocked"
    if has_events or is_monitored:
        return "relevant"           # atividade vence sempre
    alive = places_verified or source_count >= 2 or has_contact
    if category == "nightclub" and alive:
        return "relevant"
    return "dormant"
```

Em `ig_state.py`, atualizar o caller (linhas 21–24) — todos esses venues têm IG por construção, então `has_contact=True`:

```python
    vhandles = {
        v.instagram for v in venues
        if venue_relevance(v.name, v.category, v.id in with_events, v.is_monitored,
                           has_contact=True) == "relevant"
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_nightlife_relevance.py tests/test_ig_state.py -v`
Expected: PASS (se `tests/test_ig_state.py` não existir com esse nome, rodar `-k ig_state` na suíte; os testes de handles continuam verdes porque o caller passa `has_contact=True`).

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/domain/nightlife_relevance.py src/nightlife/persistence/ig_state.py tests/test_nightlife_relevance.py
git commit -m "feat: venue_relevance v2 (pin so corroborado-ou-ativo)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 8: API — sinais de vivacidade no `list_venues`

**Files:**
- Modify: `src/nightlife/api/main.py` (função `list_venues`)
- Test: `tests/test_api.py` (adicionar 1 + atualizar 2 que quebram DE PROPÓSITO)

- [ ] **Step 1: Write the failing test + atualizar os 2 existentes**

Adicionar em `tests/test_api.py` (o arquivo já importa `Venue`; adicionar `VenueSource` ao import de models):

```python
def test_venues_v2_esconde_fantasma_e_mostra_verificado(session):
    fantasma = Venue(name="Fantasma RA", category="nightclub", lat=-23.5, lng=-46.6,
                     status="unverified", confidence=0)
    verificado = Venue(name="Selva Club", category="nightclub", lat=-23.55, lng=-46.65,
                       status="operational", confidence=30)
    session.add_all([fantasma, verificado])
    session.flush()
    session.add(VenueSource(venue_id=fantasma.id, source_type="ra", source_url="u1"))
    session.add(VenueSource(venue_id=verificado.id, source_type="google_places", source_url="P1"))
    session.flush()
    client = _client(session)
    try:
        names = [x["name"] for x in client.get("/venues").json()]
        assert "Selva Club" in names and "Fantasma RA" not in names
        all_names = [x["name"] for x in client.get("/venues", params={"include_all": "true"}).json()]
        assert "Fantasma RA" in all_names        # escape hatch preservado
    finally:
        app.dependency_overrides.clear()
```

ATUALIZAR os 2 testes que a regra v2 quebra de propósito (nightclub-sem-sinais agora é dormant):
- `test_venues_sorted_by_effective_confidence_desc`: adicionar `is_monitored=True` aos DOIS venues ("Fraco" e "Forte").
- `test_venues_esconde_dormant_e_buffet_por_padrao`: no venue "Club Real", adicionar `instagram="clubreal"` (vira `has_contact` → relevant).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -v`
Expected: `test_venues_v2_esconde_fantasma_e_mostra_verificado` FALHA (fantasma ainda aparece — a API não passa os sinais). Os 2 atualizados podem passar já (ganharam sinais).

- [ ] **Step 3: Write minimal implementation**

Em `api/main.py`: adicionar aos imports `from sqlalchemy import distinct, func, select` (o `select` já existe — completar) e `from ..models import Event, Venue, VenueSource`. Substituir o bloco `if not include_all:` do `list_venues` por:

```python
    if not include_all:
        with_events = set(session.scalars(
            select(Event.venue_id).where(Event.venue_id.is_not(None))
        ).all())
        source_counts = dict(session.execute(
            select(VenueSource.venue_id, func.count(distinct(VenueSource.source_type)))
            .group_by(VenueSource.venue_id)
        ).all())
        gp_ids = set(session.scalars(
            select(distinct(VenueSource.venue_id))
            .where(VenueSource.source_type == "google_places")
        ).all())
        venues = [
            v for v in venues
            if venue_relevance(
                v.name, v.category, v.id in with_events, v.is_monitored,
                places_verified=v.id in gp_ids,
                business_status=v.business_status,
                source_count=source_counts.get(v.id, 0),
                has_contact=bool(v.instagram or v.website),
            ) == "relevant"
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -v`
Expected: PASS (todos, incluindo o novo)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/api/main.py tests/test_api.py
git commit -m "feat: /venues filtra por vivacidade (sinais places/fontes/contato)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 9: suíte completa + migration real + smoke real (CONTROLADOR)

**Files:** nenhum novo (verificação). Executado pelo controlador (precisa da `GOOGLE_MAPS_API_KEY`).

- [ ] **Step 1: Suítes completas**

Run: `.venv/Scripts/python -m pytest --basetemp="<scratchpad>/bt"` e (de `web/`) `npx vitest run`
Expected: tudo verde (exit 0); conferir por exit code, não pela contagem textual.

- [ ] **Step 2: Migration no banco real**

Run: `.venv/Scripts/python -m alembic upgrade head`
Expected: `c3d4e5f6a7b8 -> d4e5f6a7b8c9`.

- [ ] **Step 3: Redescoberta densificada (chamadas reais)**

Run: `GOOGLE_MAPS_API_KEY=... .venv/Scripts/python -m nightlife.discover_places` (em background — subdivisão pode levar minutos)
Expected: `found` bem maior que os 329 da rodada 1 (sementes novas + subdivisão); logs de subdivisão nos saturados.

- [ ] **Step 4: Enrichment + reconciliação (chamadas reais)**

Run: `GOOGLE_MAPS_API_KEY=... .venv/Scripts/python -m nightlife.enrich_places` (em background)
Expected: report `enrich: {enriched=~500-800, renamed=N, ...}` + `reconcile: {consolidated=N, superseded=~30+, ...}`.

- [ ] **Step 5: Verificações do caso-teste (SQL)**

- Selva: `SELECT id, name, website, business_status FROM venues WHERE name ILIKE '%selva%'` → "Selva Club", site selva.club, OPERATIONAL. **Nenhum** "Inferno Club" restante (fundido).
- Beco 203: sumiu (fundido no Kat Klub); Kat Klub aparece UMA vez.
- Contagem de pins: `GET /venues` → ~200–450 (vs 760 antes).
- Re-run `enrich_places` → `skipped_cached` alto, ~0 chamadas (cache 30d).

- [ ] **Step 6: Commit de ajustes do smoke (se houver)**

```bash
git add -A
git commit -m "chore: ajustes do smoke do Ciclo A

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

## Notas de implementação

- **Zero rede nos testes:** Details/Nearby sempre por fakes injetados.
- **Testes que quebram DE PROPÓSITO com a v2** (atualizados nos Tasks 7–8): `test_venue_relevance` (reescrito), `test_venues_sorted_by_effective_confidence_desc` (+`is_monitored`), `test_venues_esconde_dormant_e_buffet_por_padrao` (+`instagram`). O caller `ig_state.py` passa `has_contact=True` (todos têm IG por construção). Nenhum outro caller existe (`grep venue_relevance` confirmado).
- **Reconciliação é O(n²) nos pares com geo** (~900 venues): o gate de distância roda ANTES do `name_similarity` (caro) — só algumas centenas de pares pagam a similaridade. Runner sob demanda, não daily.
- **`_pick_survivor` e `_haversine_km` são privados de outros módulos** — importá-los é aceitável dentro do projeto (mesmo padrão de uso interno).
- **Custo do smoke:** ~US$15–25 (redescoberta + Details completo), uma vez; re-runs seguram no cache.
