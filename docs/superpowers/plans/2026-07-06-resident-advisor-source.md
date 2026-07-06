# Fonte Resident Advisor (RA) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma fonte `RASource` que puxa os eventos futuros de SP do Resident Advisor (GraphQL, via httpx) — com venue embutido (nome+endereço, sem geo) — pro banco via o pipeline existente, enchendo a lista com a programação real dos clubes.

**Architecture:** Spec: `docs/superpowers/specs/2026-07-06-resident-advisor-source-design.md`. `parse_ra_events` é PURO (testado com fixture do shape real do RA); `RASource` é a casca httpx (SP area id=400, pagina `eventListings`). Reusa `run_ingestion` — não toca no core. Runner `ingest_ra`, adicionado ao orquestrador diário.

**Tech Stack:** Python 3.14, httpx + truststore (Avast), SQLAlchemy 2.0, pytest. RA GraphQL `https://ra.co/graphql` (endpoint acessível via httpx puro; introspection ON; SP = area `400`).

**Convenções:**
- **cwd do shell RESETA entre chamadas Bash** — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Python: `.venv/Scripts/python`. Testes: `.venv/Scripts/python -m pytest ... --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife` (SEMPRE; confie no exit code — a linha "N passed" some no pipe).
- Suíte backend hoje = **154**. Commits com trailer `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`. **NÃO** mexa em `web/`.

---

## File Structure

```
src/nightlife/ingestion/ra_source.py   # NOVO — parse_ra_events (puro) + RASource (httpx)
src/nightlife/ingest_ra.py             # NOVO — runner
src/nightlife/daily.py                 # MODIFICA — + ingest_ra no STEPS
tests/test_ra_source.py                # NOVO
```

## Contexto de código (padrões a seguir)

- `ingestion/base.py`: `RawVenue(name, source_type, lat=None, lng=None, address=None, category=None, source_url=None, raw_payload="")` e `RawEvent(name, source_type, starts_at=None, ends_at=None, venue=None, venue_name=None, lineup_text=None, organizer_name=None, genre=None, ticket_url=None, source_url=None, raw_payload="")`.
- `extraction/base.py`: `parse_iso(s)` — ISO → datetime (naive se sem tz).
- `ingestion/sympla_source.py` é o molde (parse puro + classe que pagina via httpx).
- `ingestion/pipeline.py::run_ingestion(session, source, *, reference, label)` faz o upsert de venue+evento+evidência a partir dos `RawEvent` (venue embutido → cria/matcheia; `run_ingestion` já existe, não muda).

---

## Task 1: `parse_ra_events` (puro)

**Files:** Create `src/nightlife/ingestion/ra_source.py`; Create `tests/test_ra_source.py`

- [ ] **Step 1: Teste que falha** — crie `tests/test_ra_source.py`:

```python
from datetime import date
from nightlife.ingestion.ra_source import parse_ra_events

# Shape real do eventListings do RA (capturado no probe; datas em 2099 = futuras).
RA_RESPONSE = {"data": {"eventListings": {"data": [
    {"event": {"id": "1", "title": "Fugaz recebe Guarizo",
               "date": "2099-07-08T00:00:00.000", "startTime": "2099-07-08T19:00:00.000",
               "contentUrl": "/events/1", "artists": [{"name": "Guarizo"}], "genres": [{"name": "House"}],
               "venue": {"id": "9", "name": "Fugaz Bar", "address": "Rua Cardeal Arcoverde, 1479",
                         "contentUrl": "/clubs/9"}}},
    {"event": {"id": "2", "title": "Baile Do Helipa",
               "date": "2099-07-08T00:00:00.000", "startTime": "2099-07-08T22:00:00.000",
               "contentUrl": "/events/2", "artists": [], "genres": [{"name": "Baile Funk"}],
               "venue": {"id": "8", "name": "TBA - Avenida X, 751", "address": None, "contentUrl": None}}},
    {"event": {"id": "3", "title": "",   # sem titulo -> descarta
               "date": "2099-07-08T00:00:00.000", "startTime": "2099-07-08T20:00:00.000",
               "contentUrl": "/events/3", "artists": [], "genres": [],
               "venue": {"id": "7", "name": "X", "address": None, "contentUrl": "/clubs/7"}}},
    {"event": {"id": "4", "title": "Evento Passado",   # passado -> descarta
               "date": "2000-01-01T00:00:00.000", "startTime": "2000-01-01T22:00:00.000",
               "contentUrl": "/events/4", "artists": [], "genres": [],
               "venue": {"id": "6", "name": "Velho", "address": None, "contentUrl": "/clubs/6"}}},
]}}}


def test_parse_ra_events():
    events = parse_ra_events(RA_RESPONSE, reference=date(2099, 1, 1))
    assert [e.name for e in events] == ["Fugaz recebe Guarizo", "Baile Do Helipa"]  # sem-titulo e passado fora

    fugaz = events[0]
    assert fugaz.source_type == "ra"
    assert fugaz.genre == "House"
    assert fugaz.lineup_text == "Guarizo"
    assert fugaz.source_url == "https://ra.co/events/1"
    assert fugaz.ticket_url == "https://ra.co/events/1"
    assert fugaz.venue is not None
    assert fugaz.venue.name == "Fugaz Bar"
    assert fugaz.venue.address == "Rua Cardeal Arcoverde, 1479"
    assert fugaz.venue.lat is None and fugaz.venue.lng is None  # RA nao da geo (0,0)
    assert fugaz.venue.category == "nightclub"
    assert fugaz.venue.source_url == "https://ra.co/clubs/9"

    baile = events[1]
    assert baile.genre == "Baile Funk"
    assert baile.venue is None  # TBA -> sem venue (nao cria lixo)


def test_parse_ra_events_vazio():
    assert parse_ra_events({}, reference=date(2099, 1, 1)) == []
    assert parse_ra_events({"data": {"eventListings": None}}, reference=date(2099, 1, 1)) == []
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ra_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — módulo/função não existe.

- [ ] **Step 3: Implementar** — crie `src/nightlife/ingestion/ra_source.py`:

```python
# src/nightlife/ingestion/ra_source.py
"""Fonte real: eventos de nightlife de SP via a API GraphQL do Resident Advisor.

O endpoint GraphQL (ra.co/graphql) e acessivel via httpx puro (o Cloudflare so
protege as paginas HTML). O parse e PURO/testavel; a classe RASource pagina.
RA da nome+endereco do venue, mas NAO da geo (location volta 0,0) — o geo vem de
dedup c/ OSM ou do Google Places depois."""
from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from ..extraction.base import parse_iso
from .base import RawEvent, RawVenue

RA_ENDPOINT = "https://ra.co/graphql"
SP_AREA_ID = 400  # area(areaUrlName="saopaulo", countryUrlCode="br") -> id 400
_SP_TZ = ZoneInfo("America/Sao_Paulo")
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

_QUERY = """query($f: FilterInputDtoInput, $ps: Int, $page: Int) {
  eventListings(filters: $f, pageSize: $ps, page: $page) {
    data { event {
      id title date startTime contentUrl
      artists { name } genres { name }
      venue { id name address contentUrl }
    } }
    totalResults
  }
}"""


def _ra_datetime(s: str | None) -> datetime | None:
    dt = parse_iso(s)
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=_SP_TZ)  # RA da hora local de SP, sem tz


def _venue_of(v: dict) -> RawVenue | None:
    """RawVenue do venue do RA. TBA (nome=endereco, sem contentUrl) -> None (nao cria lixo)."""
    name = (v.get("name") or "").strip()
    if not name or name.upper().startswith("TBA"):
        return None
    content = v.get("contentUrl")
    return RawVenue(
        name=name,
        source_type="ra",
        lat=None, lng=None,  # RA nao expoe geo (location=0,0)
        address=(v.get("address") or "").strip() or None,
        category="nightclub",  # RA so lista nightlife
        source_url=f"https://ra.co{content}" if content else None,
    )


def parse_ra_events(data: dict, *, reference: date) -> list[RawEvent]:
    """JSON do eventListings do RA -> RawEvents. Puro. Descarta sem titulo e passados (dia SP)."""
    listings = ((data.get("data") or {}).get("eventListings")) or {}
    out: list[RawEvent] = []
    for edge in listings.get("data") or []:
        e = edge.get("event") or {}
        title = (e.get("title") or "").strip()
        if not title:
            continue
        starts = _ra_datetime(e.get("startTime") or e.get("date"))
        if starts is not None and starts.astimezone(_SP_TZ).date() < reference:
            continue
        artists = [a.get("name") for a in (e.get("artists") or []) if a.get("name")]
        genres = e.get("genres") or []
        content = e.get("contentUrl")
        url = f"https://ra.co{content}" if content else None
        out.append(RawEvent(
            name=title,
            source_type="ra",
            starts_at=starts,
            venue=_venue_of(e.get("venue") or {}),
            lineup_text=", ".join(artists) or None,
            genre=(genres[0].get("name") if genres else None),
            ticket_url=url,
            source_url=url,
            raw_payload=json.dumps(e, ensure_ascii=False, sort_keys=True),
        ))
    return out
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ra_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (2).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/ra_source.py tests/test_ra_source.py && git commit -m "feat(ra): parse_ra_events — eventListings do RA -> RawEvents (puro)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: `RASource` (paginação httpx) + runner `ingest_ra`

**Files:** Modify `src/nightlife/ingestion/ra_source.py`; Create `src/nightlife/ingest_ra.py`; append em `tests/test_ra_source.py`

- [ ] **Step 1: Teste que falha** — em `tests/test_ra_source.py`, ADICIONE ao final:

```python
from nightlife.ingestion import ra_source


def test_ra_source_paginates_e_para(monkeypatch):
    ev = {"event": {"id": "1", "title": "E", "date": "2099-07-08T00:00:00.000",
                    "startTime": "2099-07-08T22:00:00.000", "contentUrl": "/events/1",
                    "artists": [], "genres": [], "venue": {"name": "V", "contentUrl": "/clubs/1"}}}
    pages = {
        1: {"data": {"eventListings": {"data": [ev, ev]}}},   # cheia (== page_size 2)
        2: {"data": {"eventListings": {"data": [ev]}}},        # < page_size -> para
    }
    seen = []

    class _Resp:
        def __init__(self, d): self._d = d
        def raise_for_status(self): pass
        def json(self): return self._d

    def fake_post(url, **kw):
        page = kw["json"]["variables"]["page"]
        seen.append(page)
        return _Resp(pages.get(page, {"data": {"eventListings": {"data": []}}}))

    monkeypatch.setattr(ra_source.httpx, "post", fake_post)
    src = ra_source.RASource(page_size=2, reference=date(2099, 1, 1))
    events = src.events()
    assert seen == [1, 2]                 # parou na pagina 2 (veio < page_size)
    assert len(events) == 3               # 2 + 1
    assert src.venues() == [] and src.event_pages() == []
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ra_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `RASource` não existe.

- [ ] **Step 3a: Implementar `RASource`** — em `src/nightlife/ingestion/ra_source.py`, ADICIONE ao final:

```python
class RASource:
    """Fonte real #3: eventos de SP via a API GraphQL do Resident Advisor."""

    def __init__(self, *, endpoint: str = RA_ENDPOINT, area_id: int = SP_AREA_ID,
                 page_size: int = 50, max_pages: int = 10,
                 reference: date | None = None, timeout: float = 40.0) -> None:
        self._endpoint = endpoint
        self._area_id = area_id
        self._page_size = page_size
        self._max_pages = max_pages
        self._reference = reference
        self._timeout = timeout

    def venues(self) -> list[RawVenue]:
        return []  # venue vem EMBUTIDO nos eventos

    def event_pages(self):
        return []

    def events(self) -> list[RawEvent]:
        reference = self._reference or date.today()
        gte = f"{reference.isoformat()}T00:00:00.000Z"
        headers = {"User-Agent": _USER_AGENT, "Content-Type": "application/json",
                   "Referer": "https://ra.co/"}
        out: list[RawEvent] = []
        for page in range(1, self._max_pages + 1):
            resp = httpx.post(
                self._endpoint,
                json={"query": _QUERY, "variables": {
                    "f": {"areas": {"eq": self._area_id}, "listingDate": {"gte": gte}},
                    "ps": self._page_size, "page": page}},
                headers=headers, timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            batch = ((data.get("data") or {}).get("eventListings") or {}).get("data") or []
            out.extend(parse_ra_events(data, reference=reference))
            if len(batch) < self._page_size:
                break
        return out
```

- [ ] **Step 3b: Runner `ingest_ra`** — crie `src/nightlife/ingest_ra.py`:

```python
# src/nightlife/ingest_ra.py
"""Ingere eventos de SP do Resident Advisor no banco.

Uso: .venv/Scripts/python -m nightlife.ingest_ra
"""
from __future__ import annotations

import truststore

truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

from datetime import date

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.pipeline import run_ingestion
from .ingestion.ra_source import RASource
from .models import Event, Venue


def main() -> None:
    with SessionLocal() as session:
        run = run_ingestion(session, RASource(reference=date.today()),
                            reference=date.today(), label="ra")
        session.commit()
        venues = session.scalar(select(func.count()).select_from(Venue))
        events = session.scalar(select(func.count()).select_from(Event))
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"DB: {venues} venues | {events} events")
        if run.errors:
            print("erros:\n" + run.errors[:2000])


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ra_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (3).
Confirme o import do runner: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -c "import nightlife.ingest_ra; print('import ok')"` → `import ok`.

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/ra_source.py src/nightlife/ingest_ra.py tests/test_ra_source.py && git commit -m "feat(ra): RASource (pagina eventListings) + runner ingest_ra

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: `ingest_ra` no orquestrador diário

**Files:** Modify `src/nightlife/daily.py`

- [ ] **Step 1: Teste que falha** — em `tests/test_daily.py`, ADICIONE ao final:

```python
def test_steps_inclui_ra():
    from nightlife.daily import STEPS
    nomes = [nome for nome, argv in STEPS]
    assert "ingest_ra" in nomes
    # ra vem antes do ig (venues do RA ancoram antes de scrapear)
    assert nomes.index("ingest_ra") < nomes.index("ingest_ig")
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_daily.py::test_steps_inclui_ra -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `ingest_ra` não está no STEPS.

- [ ] **Step 3: Implementar** — em `src/nightlife/daily.py`, no `STEPS`, adicione a linha do `ingest_ra` logo após `discover_handles` (fica assim):

```python
STEPS: list[tuple[str, list[str]]] = [
    ("discover_handles", [sys.executable, "-m", "nightlife.discover_handles"]),
    ("ingest_ra", [sys.executable, "-m", "nightlife.ingest_ra"]),
    ("ingest_ig", [sys.executable, "-m", "nightlife.ingest_ig"]),
    ("ingest_flyers", [sys.executable, "-m", "nightlife.ingest_flyers"]),
]
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_daily.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (8 — 7 + o novo).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/daily.py tests/test_daily.py && git commit -m "feat(ra): ingest_ra no orquestrador diario (antes do ig)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 4: Suíte + smoke real (RA de verdade)

**Files:** nenhum de produção novo.

- [ ] **Step 1: Suíte inteira verde**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife -p no:cacheprovider; echo "exit: $?"`
Expected: `exit: 0` (154 + 4 novos = 158).

- [ ] **Step 2: Smoke real — puxar SP do RA de verdade e provar que entra no banco**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m nightlife.ingest_ra`
Expected: imprime `IngestionRun #N: status=finished found=<>0 created=<>0` e as contagens de venues/events subindo (dezenas de eventos de SP entram; clubes que o OSM não tinha aparecem). Cole a saída. Se `found=0`, investigue (área/shape podem ter mudado — a introspection do RA ajuda a re-pinar; mas NÃO altere os testes/parse sem diagnosticar).

- [ ] **Step 3: Verificar o efeito**

Run:
```bash
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -c "
from nightlife.db import SessionLocal
from nightlife.models import Event, EventSource, Venue
from sqlalchemy import select, func
with SessionLocal() as s:
    ra_ev = s.scalar(select(func.count()).select_from(EventSource).where(EventSource.source_type=='ra'))
    print('evidencias de evento RA:', ra_ev)
    print('total venues:', s.scalar(select(func.count()).select_from(Venue)), '| events:', s.scalar(select(func.count()).select_from(Event)))
"
```
Expected: evidências RA > 0; total de venues/events maior que antes. Cole a saída.

- [ ] **Step 4:** (sem commit obrigatório — verificação.)

---

## Coverage map (plano ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §4 `parse_ra_events` puro (venue+address, TBA, lineup, genre, passado) | Task 1 |
| §4/§6 `RASource` (SP=400, pagina eventListings) + runner `ingest_ra` | Task 2 |
| §6 `ingest_ra` no STEPS do daily | Task 3 |
| §7/§9 suíte verde + smoke real (clubes de SP no banco) | Task 4 |

**Fora deste plano (spec §8):** geocoding (Google Places — próximo sub-projeto), páginas de artista/promoter, ticketing, cidades além de SP, scraping do HTML.
