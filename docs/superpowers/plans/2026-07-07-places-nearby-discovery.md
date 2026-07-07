# Google Places Nearby Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Descobrir venues de vida noturna por geografia via Google Places API (New) Nearby Search em pontos-semente dos bairros de balada de SP, ingerindo-os pelo pipeline existente (dedup por geo + place_id).

**Architecture:** Uma `PlacesSource` que implementa o protocolo `Source` do projeto: `venues()` itera pontos-semente × tipos, chama o `PlacesClient` (httpx, um Client reutilizado) e devolve `RawVenue` com geo e `source_url=place_id`. Passa pelo `run_ingestion` → `upsert_venue` → dedup de sempre. Runner `discover_places` sob demanda (fora do daily).

**Tech Stack:** Python 3.14, SQLAlchemy 2.0, httpx + truststore, pytest, Postgres (porta 5434). Places API (New) `places:searchNearby`.

**Referências do código existente (assinaturas verificadas):**
- `nightlife.ingestion.base`: `RawVenue(name, source_type, lat=None, lng=None, address=None, category=None, source_url=None, raw_payload="")`; protocolo `Source` = `venues()`/`event_pages()`/`events()` (todos `Iterable`).
- `nightlife.ingestion.pipeline.run_ingestion(session, source, *, reference: date, label: str = "mock") -> IngestionRun`.
- `nightlife.ingestion.mock_source.MockSource(venues_list, event_pages_list, events=[...])` — para testes de pipeline.
- `nightlife.models.Venue(id, name, category, lat, lng, address, ..., confidence)`, `VenueSource(venue_id, source_type, source_url, ...)`.
- `nightlife.config.GOOGLE_MAPS_API_KEY` (já existe).
- `source_type="google_places"` já está em `VENUE_SOURCE_CONTRIBUTION` (=30) em `persistence/confidence.py`.
- Padrão de runner (ver `src/nightlife/geocode_venues.py`): `truststore.inject_into_ssl()`, lê a chave, `with SessionLocal() as session: ... session.commit()`.
- Lição do geocoding: **reusar UM `httpx.Client`** (a função `httpx.get`/`httpx.post` por chamada constrói um Client novo → `OSError Errno 24` em centenas de chamadas).

**Convenção de commit:** cada commit termina com o trailer `Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu`.

**Testes:** `.venv/Scripts/python -m pytest <arquivo>::<teste> -v`. Se `tmp_path` estourar `PermissionError WinError 5`, rodar a suíte completa com `--basetemp=<scratchpad>/bt`.

---

### Task 1: `places_client.py` — cliente Places (New) injetável

**Files:**
- Create: `src/nightlife/ingestion/places_client.py`
- Test: `tests/test_places_client.py`

Contexto: `PlacesClient.search_nearby` faz um POST real ao `places:searchNearby`, então o teste injeta um client fake (zero rede) e testa o parsing. `PlaceResult` é o contrato que a `PlacesSource` consome.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_places_client.py
import httpx

from nightlife.ingestion.places_client import PlacesClient, PlaceResult


def _fake_response(payload):
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return payload
    return _Resp()


class _FakeClient:
    """Client injetavel: responde um payload fixo (ou levanta); conta chamadas."""
    def __init__(self, payload=None, raises=None):
        self.payload = payload
        self.raises = raises
        self.calls = 0

    def post(self, url, headers=None, json=None):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return _fake_response(self.payload)


def _client(payload=None, raises=None):
    return PlacesClient("KEY", client=_FakeClient(payload=payload, raises=raises))


def test_parse_resultado_ok():
    payload = {"places": [
        {"id": "PID1", "displayName": {"text": "Supra Club Augusta"},
         "location": {"latitude": -23.55, "longitude": -46.66},
         "formattedAddress": "Rua Augusta, 500", "primaryType": "night_club"},
    ]}
    res = _client(payload).search_nearby(-23.55, -46.66, 1000, "night_club")
    assert res == [PlaceResult(place_id="PID1", name="Supra Club Augusta", lat=-23.55,
                               lng=-46.66, address="Rua Augusta, 500", primary_type="night_club")]


def test_descarta_sem_id_ou_sem_location():
    payload = {"places": [
        {"displayName": {"text": "Sem Id"}, "location": {"latitude": -23.5, "longitude": -46.6}},
        {"id": "PID2", "displayName": {"text": "Sem Geo"}},
    ]}
    assert _client(payload).search_nearby(-23.5, -46.6, 1000, "night_club") == []


def test_erro_de_rede_vira_lista_vazia():
    assert _client(raises=httpx.ConnectError("sem rede")).search_nearby(-23.5, -46.6, 1000, "night_club") == []


def test_resposta_de_erro_json_vira_lista_vazia():
    # a Places devolve {"error": {...}} e sem "places"
    res = _client({"error": {"code": 403, "status": "PERMISSION_DENIED"}}).search_nearby(-23.5, -46.6, 1000, "night_club")
    assert res == []


def test_reusa_um_unico_client(monkeypatch):
    # regressao Errno 24: um Client por PlacesClient, nao um por chamada
    constructed = []
    real_init = httpx.Client.__init__

    def _counting_init(self, *a, **k):
        constructed.append(1)
        real_init(self, *a, **k)

    monkeypatch.setattr(httpx.Client, "__init__", _counting_init)
    monkeypatch.setattr(httpx.Client, "post",
                        lambda self, *a, **k: _fake_response({"places": []}))
    c = PlacesClient("KEY")   # sem client injetado -> constroi o proprio
    c.search_nearby(-23.5, -46.6, 1000, "night_club")
    c.search_nearby(-23.5, -46.6, 1000, "dance_hall")
    assert len(constructed) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_places_client.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'nightlife.ingestion.places_client'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/nightlife/ingestion/places_client.py
"""Cliente da Google Places API (New) — Nearby Search (places:searchNearby).

Descoberta geografica: dado ponto+raio+tipo, devolve os lugares COM geo e
place_id. Um httpx.Client reutilizado (senao Errno 24 em muitas chamadas). Field
mask no tier Pro (id/nome/geo/endereco/tipo) — sem rating/reviews, custo menor."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

_ENDPOINT = "https://places.googleapis.com/v1/places:searchNearby"
_FIELD_MASK = ("places.id,places.displayName,places.location,"
               "places.formattedAddress,places.primaryType")
_TIMEOUT = 20.0


@dataclass(frozen=True)
class PlaceResult:
    place_id: str
    name: str
    lat: float
    lng: float
    address: str | None
    primary_type: str | None


class PlacesClient:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.Client(timeout=_TIMEOUT)

    def search_nearby(self, lat: float, lng: float, radius: float,
                      included_type: str) -> list[PlaceResult]:
        body = {
            "includedTypes": [included_type],
            "maxResultCount": 20,
            "rankPreference": "DISTANCE",
            "locationRestriction": {"circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius)}},
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }
        try:
            resp = self._client.post(_ENDPOINT, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []

        out: list[PlaceResult] = []
        for p in data.get("places", []):
            loc = p.get("location") or {}
            pid, lat_, lng_ = p.get("id"), loc.get("latitude"), loc.get("longitude")
            if not pid or lat_ is None or lng_ is None:
                continue  # sem identidade ou sem geo: descarta defensivamente
            out.append(PlaceResult(
                place_id=pid,
                name=(p.get("displayName") or {}).get("text", ""),
                lat=lat_, lng=lng_,
                address=p.get("formattedAddress"),
                primary_type=p.get("primaryType"),
            ))
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_places_client.py -v`
Expected: PASS (5 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/ingestion/places_client.py tests/test_places_client.py
git commit -m "feat: PlacesClient (Places New searchNearby, um Client reutilizado)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 2: `places_source.py` — Source de descoberta

**Files:**
- Create: `src/nightlife/ingestion/places_source.py`
- Test: `tests/test_places_source.py`

Contexto: `PlacesSource` implementa o protocolo `Source`. `venues()` itera semente×tipo, chama o client, mapeia `PlaceResult → RawVenue` (categoria pelo primaryType, place_id → source_url), e loga quando um par satura (>=20). `event_pages()`/`events()` retornam `[]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_places_source.py
from nightlife.ingestion.base import RawVenue
from nightlife.ingestion.places_client import PlaceResult
from nightlife.ingestion.places_source import PlacesSource, _category_for, SEED_POINTS, SEARCH_TYPES


class _FakePlacesClient:
    """Devolve resultados por tipo e registra as chamadas."""
    def __init__(self, by_type=None):
        self.by_type = by_type or {}
        self.calls = []

    def search_nearby(self, lat, lng, radius, included_type):
        self.calls.append((lat, lng, radius, included_type))
        return list(self.by_type.get(included_type, []))


def test_category_for_mapeia_por_primary_type():
    assert _category_for("night_club") == "nightclub"
    assert _category_for("dance_hall") == "nightclub"
    assert _category_for("live_music_venue") == "nightclub"
    assert _category_for("concert_hall") == "nightclub"
    assert _category_for("bar") == "bar"          # vazou via tipo secundario
    assert _category_for(None) == "bar"


def test_venues_itera_semente_x_tipo_e_mapeia():
    pr = PlaceResult(place_id="PID1", name="Supra Club Augusta", lat=-23.55, lng=-46.66,
                     address="Rua Augusta, 500", primary_type="night_club")
    client = _FakePlacesClient(by_type={"night_club": [pr]})
    src = PlacesSource(client, seeds=[("Augusta", -23.5545, -46.6620)],
                       types=("night_club", "dance_hall"), radius=1000)
    vs = list(src.venues())
    # 1 semente x 2 tipos = 2 chamadas
    assert len(client.calls) == 2
    assert client.calls[0] == (-23.5545, -46.6620, 1000, "night_club")
    # so night_club retornou algo
    assert vs == [RawVenue(name="Supra Club Augusta", source_type="google_places",
                           lat=-23.55, lng=-46.66, address="Rua Augusta, 500",
                           category="nightclub", source_url="PID1")]


def test_venues_loga_saturacao_em_20():
    lots = [PlaceResult(place_id=f"P{i}", name=f"Club {i}", lat=-23.5, lng=-46.6,
                        address=None, primary_type="night_club") for i in range(20)]
    client = _FakePlacesClient(by_type={"night_club": lots})
    logs = []
    src = PlacesSource(client, seeds=[("Augusta", -23.5, -46.6)],
                       types=("night_club",), radius=1000, log=logs.append)
    list(src.venues())
    assert any("satur" in m.lower() for m in logs)


def test_event_pages_e_events_vazios():
    src = PlacesSource(_FakePlacesClient())
    assert list(src.event_pages()) == []
    assert list(src.events()) == []


def test_defaults_de_seeds_e_types_existem():
    assert len(SEED_POINTS) >= 10
    assert "night_club" in SEARCH_TYPES and "event_venue" not in SEARCH_TYPES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_places_source.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'nightlife.ingestion.places_source'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/nightlife/ingestion/places_source.py
"""Source de descoberta geografica via Google Places Nearby (spec §4B).

Itera pontos-semente dos bairros de balada de SP x tipos de nightlife, chama o
PlacesClient e devolve RawVenue com geo + place_id (identidade estavel para o
dedup). event_venue foi descartado no design (ruido: buffet/casamento)."""
from __future__ import annotations

from typing import Callable, Iterable

from .base import RawEvent, RawEventPage, RawVenue
from .places_client import PlacesClient

SEARCH_TYPES = ("night_club", "dance_hall", "live_music_venue", "concert_hall")

# centroides aproximados de bairros de balada de SP (precisao coberta pelo raio)
SEED_POINTS: list[tuple[str, float, float]] = [
    ("Augusta/Consolacao", -23.5545, -46.6620),
    ("Vila Madalena",      -23.5560, -46.6900),
    ("Barra Funda",        -23.5260, -46.6640),
    ("Lapa",               -23.5230, -46.7050),
    ("Itaim/Vila Olimpia", -23.5850, -46.6790),
    ("Pinheiros",          -23.5670, -46.6950),
    ("Centro/Republica",   -23.5440, -46.6420),
    ("Bela Vista/Bexiga",  -23.5580, -46.6450),
    ("Vila Mariana",       -23.5890, -46.6340),
    ("Moema",              -23.6000, -46.6650),
    ("Santana",            -23.5030, -46.6250),
    ("Tatuape",            -23.5400, -46.5760),
    ("Brooklin/Berrini",   -23.6100, -46.6900),
    ("Perdizes/Pompeia",   -23.5320, -46.6820),
]
_SEARCH_RADIUS_M = 1000

_NIGHTCLUB_TYPES = {"night_club", "dance_hall", "live_music_venue", "concert_hall"}


def _category_for(primary_type: str | None) -> str:
    return "nightclub" if primary_type in _NIGHTCLUB_TYPES else "bar"


class PlacesSource:
    def __init__(self, client: PlacesClient, *, seeds=SEED_POINTS,
                 types=SEARCH_TYPES, radius: float = _SEARCH_RADIUS_M,
                 log: Callable[[str], None] = print) -> None:
        self._client = client
        self._seeds = seeds
        self._types = types
        self._radius = radius
        self._log = log

    def venues(self) -> Iterable[RawVenue]:
        for name, lat, lng in self._seeds:
            for t in self._types:
                results = self._client.search_nearby(lat, lng, self._radius, t)
                if len(results) >= 20:
                    self._log(f"[places] saturou 20 em {name!r}/{t} (sinal p/ grade futura)")
                for r in results:
                    yield RawVenue(
                        name=r.name, source_type="google_places",
                        lat=r.lat, lng=r.lng, address=r.address,
                        category=_category_for(r.primary_type), source_url=r.place_id,
                    )

    def event_pages(self) -> Iterable[RawEventPage]:
        return []

    def events(self) -> Iterable[RawEvent]:
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_places_source.py -v`
Expected: PASS (5 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/ingestion/places_source.py tests/test_places_source.py
git commit -m "feat: PlacesSource (semente x tipo -> RawVenue, categoria por primaryType)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 3: dedup no pipeline — venue do Places funde/idempotente

**Files:**
- Test: `tests/test_pipeline_places.py` (só teste — verifica comportamento do pipeline existente)

Contexto: não muda código de produção; comprova que um `RawVenue` do Places (com geo + place_id) faz o que o design promete: funde com um venue existente próximo de nome similar (auto_merge), e re-ingerir o mesmo place_id é idempotente. Usa `MockSource` + `run_ingestion`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline_places.py
from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue, VenueSource
from nightlife.ingestion.base import RawVenue
from nightlife.ingestion.mock_source import MockSource
from nightlife.ingestion.pipeline import run_ingestion

REF = date(2026, 6, 1)


def _places_venue(name, pid, lat, lng):
    return RawVenue(name=name, source_type="google_places", lat=lat, lng=lng,
                    address="Rua Augusta, 500", category="nightclub", source_url=pid)


def test_places_venue_funde_com_existente_proximo(session):
    # ja existe "Club Aloka" (ex.: veio do RA) com geo; o Places traz "Aloka Club"
    # no mesmo lugar -> auto_merge (1 venue), place_id vira evidencia google_places
    existing = Venue(name="Club Aloka", lat=-23.5550, lng=-46.6620, category="nightclub")
    session.add(existing)
    session.flush()
    rv = _places_venue("Aloka Club", "PID_ALOKA", -23.5551, -46.6621)
    run_ingestion(session, MockSource([rv], []), reference=REF, label="places")
    session.flush()

    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    src = session.scalars(select(VenueSource).where(
        VenueSource.source_type == "google_places", VenueSource.source_url == "PID_ALOKA")).first()
    assert src is not None and src.venue_id == existing.id


def test_places_venue_novo_e_criado(session):
    rv = _places_venue("Supra Club Augusta", "PID_SUPRA", -23.5545, -46.6620)
    run_ingestion(session, MockSource([rv], []), reference=REF, label="places")
    session.flush()
    v = session.scalars(select(Venue).where(Venue.name == "Supra Club Augusta")).one()
    assert v.category == "nightclub" and v.lat == -23.5545


def test_places_reingest_mesmo_place_id_e_idempotente(session):
    rv = _places_venue("Supra Club Augusta", "PID_SUPRA", -23.5545, -46.6620)
    run_ingestion(session, MockSource([rv], []), reference=REF, label="places")
    session.flush()
    run_ingestion(session, MockSource([rv], []), reference=REF, label="places")
    session.flush()
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    # uma unica linha de evidencia para o place_id
    n = session.scalar(select(func.count()).select_from(VenueSource).where(
        VenueSource.source_url == "PID_SUPRA"))
    assert n == 1
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `.venv/Scripts/python -m pytest tests/test_pipeline_places.py -v`
Expected: PASS diretamente (o pipeline/upsert já suportam geo + source_url). Se algum falhar, é um bug real de integração a investigar (NÃO relaxar o teste sem entender). Documente e escale se o comportamento divergir do design §5.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pipeline_places.py
git commit -m "test: dedup de venue do Places no pipeline (auto_merge + idempotencia por place_id)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 4: `discover_places.py` — runner sob demanda

**Files:**
- Create: `src/nightlife/discover_places.py`
- Test: `tests/test_discover_places.py`

Contexto: `discover(session, client, *, reference)` é o núcleo testável (recebe o `PlacesClient` injetado, roda `run_ingestion`, retorna o `IngestionRun`). `main()` lê a chave, monta o client real e commita. Espelha o split `geocode_all`/`main` do geocoding.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_places.py
from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue
from nightlife.ingestion.places_client import PlaceResult
from nightlife.discover_places import discover

REF = date(2026, 6, 1)


class _FakePlacesClient:
    def __init__(self, by_type=None):
        self.by_type = by_type or {}

    def search_nearby(self, lat, lng, radius, included_type):
        return list(self.by_type.get(included_type, []))


def test_discover_cria_venues(session):
    pr = PlaceResult(place_id="PID1", name="Supra Club Augusta", lat=-23.55, lng=-46.66,
                     address="Rua Augusta, 500", primary_type="night_club")
    from nightlife.ingestion.places_source import PlacesSource
    src = PlacesSource(_FakePlacesClient({"night_club": [pr]}),
                       seeds=[("Augusta", -23.5545, -46.6620)], types=("night_club",))
    run = discover(session, src, reference=REF)
    session.flush()
    assert run.status == "finished"
    assert session.scalar(select(func.count()).select_from(Venue)) == 1


def test_discover_reingest_idempotente(session):
    pr = PlaceResult(place_id="PID1", name="Supra Club Augusta", lat=-23.55, lng=-46.66,
                     address="Rua Augusta, 500", primary_type="night_club")
    from nightlife.ingestion.places_source import PlacesSource
    mk = lambda: PlacesSource(_FakePlacesClient({"night_club": [pr]}),
                              seeds=[("Augusta", -23.5545, -46.6620)], types=("night_club",))
    discover(session, mk(), reference=REF)
    session.flush()
    discover(session, mk(), reference=REF)
    session.flush()
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_discover_places.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'nightlife.discover_places'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/nightlife/discover_places.py
"""Descobre venues de vida noturna via Google Places Nearby e ingere pelo
pipeline. Sob demanda (fora do daily): venue novo e raro e cada chamada custa.

Uso: .venv/Scripts/python -m nightlife.discover_places
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ingestion.pipeline import run_ingestion
from .ingestion.places_source import PlacesSource
from .models import IngestionRun, Venue

_SP_TZ = ZoneInfo("America/Sao_Paulo")


def discover(session: Session, source: PlacesSource, *, reference: date) -> IngestionRun:
    return run_ingestion(session, source, reference=reference, label="places")


def main() -> None:
    from .config import GOOGLE_MAPS_API_KEY

    if not GOOGLE_MAPS_API_KEY:
        print("ERRO: defina GOOGLE_MAPS_API_KEY (e habilite a Places API New no Google Cloud)")
        sys.exit(1)

    import truststore
    truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

    from .db import SessionLocal
    from .ingestion.places_client import PlacesClient

    today = datetime.now(_SP_TZ).date()
    with SessionLocal() as session:
        run = discover(session, PlacesSource(PlacesClient(GOOGLE_MAPS_API_KEY)), reference=today)
        session.commit()
        total = session.scalar(select(func.count()).select_from(Venue))
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"DB: {total} venues")
        if run.errors:
            print("erros:\n" + run.errors[:2000])


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_discover_places.py -v`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/discover_places.py tests/test_discover_places.py
git commit -m "feat: runner discover_places (Places Nearby sob demanda)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 5: suíte completa + smoke real

**Files:** nenhum novo (verificação).

- [ ] **Step 1: Rodar a suíte inteira**

Run: `.venv/Scripts/python -m pytest -q --basetemp="<scratchpad>/bt"`
Expected: todos verdes (os anteriores + os novos deste plano). Conferir via exit code (`echo $?` = 0), não pela contagem textual (o pipe `\r` do Windows distorce).

- [ ] **Step 2: Smoke real (precisa da chave + Places API New habilitada)**

Pré-requisito: `GOOGLE_MAPS_API_KEY` no ambiente e a **Places API (New)** habilitada no projeto. Sem isso, pular e reportar.

Run: `.venv/Scripts/python -m nightlife.discover_places`
Expected: `found>0 created>0`, o total de venues sobe. Confirmar no banco: `SELECT * FROM venues WHERE name ILIKE '%supra%'` traz "Supra Club Augusta"; contar nightclubs com geo na Augusta subiu; buscar a Selva (`name ILIKE '%selv%'`).

- [ ] **Step 3: Confirmar idempotência**

Run: `.venv/Scripts/python -m nightlife.discover_places` (segunda vez)
Expected: `created` ~0 (place_id já conhecido) e a contagem de venues **não** cresce.

- [ ] **Step 4: Commit (se algum ajuste de smoke foi necessário)**

Se nada mudou no código, não há commit. Caso ajustes tenham sido feitos:

```bash
git add -A
git commit -m "chore: ajustes do smoke real de descoberta Places

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

## Notas de implementação

- **Zero rede nos testes:** `PlacesClient` recebe um `httpx.Client` fake; `PlacesSource`/`discover` recebem um `PlacesClient` fake. Nenhum teste toca a Google.
- **Um Client reutilizado:** repetição da lição do geocoding (Errno 24). O teste `test_reusa_um_unico_client` guarda isso.
- **Dedup é do pipeline existente:** a Task 3 só comprova; não há novo código de dedup. Se um teste da Task 3 falhar, é bug de integração real — investigar, não relaxar.
- **Custo:** ~14 sementes × 4 tipos ≈ 56 chamadas/run (Nearby Pro SKU) ≈ US$1.80. Sob demanda.
