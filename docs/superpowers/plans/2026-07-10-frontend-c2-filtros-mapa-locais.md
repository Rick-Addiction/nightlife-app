# Ciclo C — Plano C-2: Filtros ricos + Mapa + Locais — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar o redesign Rave Brutalista: sheet de filtros avançado (QUANDO/ONDE/SOM/EXTRAS/CONFIANÇA com botão-resultado vivo) igual nas abas FESTAS e MAPA, MapaTab completo (gaveta arrastável + CAMADAS), LocaisTab vivo (busca + badges de vivacidade), `VenueOut.ig_last_post_at`+`places_verified` no backend, PWA manifest, e os débitos M1 (sidecars `.json` servidos) e M3 (mkdir em import-time).

**Architecture:** Continuação do rebuild-in-place (spec `2026-07-10-frontend-redesign-design.md`, §4 Plano C-2). Filtros novos são **client-side** sobre o array joinado (`filters/apply.ts`); presets de QUANDO continuam indo pra API (`date_from/date_to`). O reducer é a única fonte de verdade (o sheet edita AO VIVO — sem estado draft; o "VER N →" só fecha). `MapView.tsx` **não muda**: MapaTab controla camadas passando `events`/`venues` já filtrados e `showVenues`. Gaveta sem lib (pointer events + helper puro de snap). LocaisTab expande o card inline (sem sheet novo).

**Tech Stack:** React 19 + Vite + TS, react-map-gl/maplibre, Vitest + Testing Library; FastAPI + pytest; Pillow (ícones PWA, já no venv).

**Referências verificadas do código atual (2026-07-10, pós C-1):**
- `filters/state.ts`: `Preset = 'upcoming'|'today'|'tomorrow'|'weekend'|'all'`; `FilterState {preset, genre: string|null, minConfidence, includePast}`; `queryFromFilters` emite `genre`/`min_confidence`/datas com `isoDate` LOCAL.
- `data/join.ts`: `EventWithGeo extends EventOut { venueName, venueInstagram, lat, lng, mappable }`.
- `api/types.ts`: `VenueOut` SEM `ig_last_post_at`/`places_verified` (adicionar).
- `api/main.py`: mount `StaticFiles` em `/flyers` + `config.FLYERS_PROCESSED_DIR.mkdir` no import (linhas 22–23 — M3); `_flyer_files()` já tolera dir ausente (`except OSError`); `list_venues` já computa `gp_ids` (venues com `VenueSource.source_type=="google_places"`) DENTRO do bloco `if not include_all:` — içar e reusar pro `places_verified`.
- `flyers/processed/` tem 34 sidecars `.json` ao lado das imagens (M1 — hoje servidos pelo mount).
- `Venue.ig_last_post_at` existe no modelo (Ciclo B, migration `e5f6a7b8c9d0`) — só expor.
- `MapView.tsx`: props `{events, venues, selectedId, onSelect, showVenues}`; mini-card de pin + popup de venue prontos; `events={[]}` esconde markers sem quebrar nada.
- `App.tsx`: `events` já é o array JOINADO (`EventWithGeo[]`); mobile mantém o mapa SEMPRE montado (display toggle, `bottom: 44`); tabbar z-index 30.
- Sementes de bairro: `ingestion/places_source.py` `SEED_POINTS` (20 pontos com lat/lng).
- Testes web: `render/screen/userEvent` (ver `FilterChips.test.tsx`); rodar `cd web && npx vitest run <arquivo>`; typecheck `npx tsc -b`. Backend: `.venv/Scripts/python -m pytest <arquivo> -v` (Postgres 5434 de pé; suíte completa com `--basetemp=.pytest-tmp` — temp default do Windows tem permissão corrompida).
- `theme.css`: classes `.chip/.chip.on/.chip.grn`, `.b-card`, `.hline`, `.label`, `.tag/.tag.ghost`, `.b-btn/.b-btn.primary`, keyframes `b-pop/b-fade/b-slide-up`. **Lição C-1:** regra p/ classes do maplibre precisa prefixo `.maplibregl-popup` (especificidade acima do css do maplibre, que entra no bundle depois).

**Convenção de commit:** trailer `Claude-Session: b9eb4ce7-361b-434d-9809-31614b56e56d`.
**Branch:** `feat/frontend-c2` (a partir do master pós C-1).

---

### Task 1: Backend — `VenueOut.ig_last_post_at` + `places_verified`

**Files:**
- Modify: `src/nightlife/api/schemas.py` (VenueOut), `src/nightlife/api/main.py` (`list_venues`, `get_venue`)
- Test: `tests/test_api_venues_c2.py` (novo)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_venues_c2.py
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from nightlife.api.deps import get_session
from nightlife.api.main import app
from nightlife.models import Venue, VenueSource


def _client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def test_ig_last_post_at_exposto(session):
    v = Venue(name="Selva Club", lat=-23.55, lng=-46.65, confidence=50,
              ig_last_post_at=datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc))
    session.add(v)
    session.flush()
    client = _client(session)
    try:
        row = next(x for x in client.get("/venues?include_all=true").json() if x["id"] == v.id)
        assert row["ig_last_post_at"] is not None
        assert row["ig_last_post_at"].startswith("2026-07-09")
        one = client.get(f"/venues/{v.id}").json()
        assert one["ig_last_post_at"].startswith("2026-07-09")
    finally:
        app.dependency_overrides.clear()


def test_places_verified_por_evidencia_google_places(session):
    com = Venue(name="D-Edge", lat=-23.52, lng=-46.66, confidence=50)
    sem = Venue(name="Bar Aleatorio", lat=-23.56, lng=-46.64, confidence=50)
    session.add_all([com, sem])
    session.flush()
    session.add(VenueSource(venue_id=com.id, source_type="google_places",
                            source_url="place:ChIJfake123"))
    session.flush()
    client = _client(session)
    try:
        rows = {x["id"]: x for x in client.get("/venues?include_all=true").json()}
        assert rows[com.id]["places_verified"] is True
        assert rows[sem.id]["places_verified"] is False
        assert client.get(f"/venues/{com.id}").json()["places_verified"] is True
        assert client.get(f"/venues/{sem.id}").json()["places_verified"] is False
    finally:
        app.dependency_overrides.clear()
```

Antes de rodar: confira no `tests/conftest.py` a fixture `session` (mesma usada por `test_api_flyers.py`) e os campos obrigatórios de `Venue`/`VenueSource` (se `VenueSource.source_url` for NOT NULL, o valor acima já cobre; ajuste kwargs se o modelo exigir mais).

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_api_venues_c2.py -v`
Expected: FAIL — `KeyError: 'ig_last_post_at'` (campo não existe no payload)

- [ ] **Step 3: Implement**

Em `schemas.py`, acrescente ao `VenueOut` (depois de `is_monitored`):

```python
    ig_last_post_at: datetime | None = None
    places_verified: bool = False
```

(`from_attributes` já popula `ig_last_post_at` a partir do modelo.)

Em `main.py::list_venues`, iça a query de `gp_ids` pra ANTES do bloco `if not include_all:` (removendo a duplicata de dentro do bloco) e marque os outs:

```python
    venues = session.scalars(q).all()
    gp_ids = set(session.scalars(
        select(distinct(VenueSource.venue_id))
        .where(VenueSource.source_type == "google_places")
    ).all())
    if not include_all:
        ...  # bloco atual, SEM a re-query de gp_ids
    now = datetime.now(timezone.utc)
    outs = [_with_effective(VenueOut, v, now) for v in venues]
    for o in outs:
        o.places_verified = o.id in gp_ids
    ...
```

Em `main.py::get_venue`:

```python
    out = _with_effective(VenueOut, venue, datetime.now(timezone.utc))
    out.places_verified = bool(session.scalar(
        select(func.count()).select_from(VenueSource)
        .where(VenueSource.venue_id == venue_id,
               VenueSource.source_type == "google_places")
    ))
    return out
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_api_venues_c2.py tests/test_api.py -v`
Expected: PASS (novos + regressão)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/api/schemas.py src/nightlife/api/main.py tests/test_api_venues_c2.py
git commit -m "feat(api): VenueOut ganha ig_last_post_at + places_verified (vivacidade do C-2)"
```

---

### Task 2: Backend — rota `/flyers/{filename}` no lugar do StaticFiles (M1 + M3)

**Files:**
- Modify: `src/nightlife/api/main.py`
- Test: `tests/test_api_flyers.py` (acrescentar)

M1: os 34 sidecars `.json` em `flyers/processed/` são servidos pelo mount. M3: `mkdir` em import-time. A rota explícita resolve os dois: só serve extensões de imagem, lê `config.FLYERS_PROCESSED_DIR` **em request-time** (nada no import; e o monkeypatch dos testes passa a valer também pro serving).

- [ ] **Step 1: Write the failing test** (acrescentar ao final de `tests/test_api_flyers.py`)

```python
def test_rota_flyers_so_serve_imagem(session, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FLYERS_PROCESSED_DIR", tmp_path)
    (tmp_path / "ABC12345678.jpg").write_bytes(b"imagem")
    (tmp_path / "ABC12345678.json").write_text("{\"caption\": \"segredo\"}")
    client = _client(session)
    try:
        assert client.get("/flyers/ABC12345678.jpg").status_code == 200
        # M1: sidecar .json NUNCA e servido
        assert client.get("/flyers/ABC12345678.json").status_code == 404
        # traversal e nomes fora do padrao shortcode
        assert client.get("/flyers/..%2Fconftest.py").status_code == 404
        assert client.get("/flyers/NAOEXISTE999.jpg").status_code == 404
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_api_flyers.py -v`
Expected: o teste novo FALHA (o `.json` responde 200 via mount; e o 200 do `.jpg` pode falhar também — o mount capturou o diretório REAL no import, não o tmp_path). Os 3 testes antigos passam.

- [ ] **Step 3: Implement** — em `main.py`:

Remova as linhas do import-time:

```python
config.FLYERS_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/flyers", StaticFiles(directory=str(config.FLYERS_PROCESSED_DIR)), name="flyers")
```

e o import `from fastapi.staticfiles import StaticFiles`. Adicione (perto de `_IG_PERMALINK`):

```python
from fastapi.responses import FileResponse

# so serve imagem com nome no formato shortcode.ext — sidecars .json e
# qualquer path fora do padrao respondem 404 (M1); dir lido em request-time (M3)
_FLYER_FILE = re.compile(r"^[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)$")


@app.get("/flyers/{filename}")
def get_flyer(filename: str):
    if not _FLYER_FILE.fullmatch(filename):
        raise HTTPException(status_code=404, detail="flyer nao encontrado")
    path = config.FLYERS_PROCESSED_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="flyer nao encontrado")
    return FileResponse(path)
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_api_flyers.py tests/test_api.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/api/main.py tests/test_api_flyers.py
git commit -m "fix(api): /flyers vira rota com allowlist de extensao (M1 sidecars) e sem mkdir no import (M3)"
```

---

### Task 3: Web — `types.ts` + `join.ts` com os campos de vivacidade

**Files:**
- Modify: `web/src/api/types.ts`, `web/src/data/join.ts`
- Test: `web/src/data/join.test.ts` (acrescentar/ajustar fixtures)

- [ ] **Step 1: Types** — em `types.ts`, acrescente ao `VenueOut`:

```ts
  ig_last_post_at: string | null
  places_verified: boolean
```

- [ ] **Step 2: Write the failing test** — em `join.test.ts`, acrescente:

```ts
it('propaga ig_last_post_at do venue para o evento joinado', () => {
  const venue = { ...baseVenue, id: 7, ig_last_post_at: '2026-07-09T03:00:00Z' }
  const evt = { ...baseEvent, venue_id: 7 }
  const [j] = joinEventsWithVenues([evt], [venue])
  expect(j.venueIgLastPostAt).toBe('2026-07-09T03:00:00Z')
})
it('evento sem venue tem venueIgLastPostAt null', () => {
  const [j] = joinEventsWithVenues([{ ...baseEvent, venue_id: null }], [])
  expect(j.venueIgLastPostAt).toBeNull()
})
```

Os literais `VenueOut` existentes no arquivo de teste deixarão de compilar — acrescente `ig_last_post_at: null, places_verified: false` às fixtures (ou a um `baseVenue` compartilhado).

- [ ] **Step 3: Run to verify it fails**

Run: `cd web && npx vitest run src/data/join.test.ts`
Expected: FAIL (`venueIgLastPostAt` undefined)

- [ ] **Step 4: Implement** — em `join.ts`:

```ts
export interface EventWithGeo extends EventOut {
  venueName: string | null
  venueInstagram: string | null
  venueIgLastPostAt: string | null
  lat: number | null
  lng: number | null
  mappable: boolean
}
```

e no map: `venueIgLastPostAt: v?.ig_last_post_at ?? null,`

- [ ] **Step 5: Run tests + typecheck**

Run: `cd web && npx vitest run src/data/join.test.ts && npx tsc -b`
Expected: PASS / sem erros (se outros testes montam `EventWithGeo`/`VenueOut` literais, complete as fixtures)

- [ ] **Step 6: Commit**

```bash
git add web/src/api/types.ts web/src/data/join.ts web/src/data/join.test.ts
git commit -m "feat(web): ig_last_post_at + places_verified nos types; join propaga vivacidade do venue"
```

---

### Task 4: Web — `data/bairros.ts` (centroides + haversine + classify)

**Files:**
- Create: `web/src/data/bairros.ts`
- Test: `web/src/data/bairros.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/data/bairros.test.ts
import { describe, it, expect } from 'vitest'
import { BAIRROS, CLASSIFY_MAX_KM, classify, distanceKm } from './bairros'

describe('bairros', () => {
  it('distanceKm: mesmo ponto = 0; Augusta -> Vila Madalena ~3-4km', () => {
    expect(distanceKm(-23.553, -46.656, -23.553, -46.656)).toBe(0)
    const d = distanceKm(-23.553, -46.656, -23.556, -46.69)
    expect(d).toBeGreaterThan(3)
    expect(d).toBeLessThan(4)
  })
  it('classify: em cima do centroide devolve o bairro', () => {
    for (const b of BAIRROS) {
      // centroides vizinhos (<1km no centro) podem "roubar" — aceita qualquer
      // bairro a <= raio, mas o proprio ponto nunca vira null
      expect(classify(b.lat, b.lng)).not.toBeNull()
    }
    expect(classify(-23.556, -46.69)).toBe('VILA MADALENA')
  })
  it('classify: longe de tudo devolve null', () => {
    expect(classify(-22.9, -43.2)).toBeNull() // Rio
    expect(classify(-23.553, -46.9)).toBeNull() // Osasco, > CLASSIFY_MAX_KM de qualquer semente
  })
  it('classify: dentro do raio-limite classifica', () => {
    // ~1km ao norte da Vila Madalena (0.009 grau de lat)
    expect(classify(-23.547, -46.69)).toBe('VILA MADALENA')
    expect(CLASSIFY_MAX_KM).toBe(2)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/data/bairros.test.ts`
Expected: FAIL (módulo não existe)

- [ ] **Step 3: Implement**

```ts
// web/src/data/bairros.ts
// Centroides = sementes do discover_places (ingestion/places_source.py),
// com nomes de exibicao; as duas sementes da Augusta viram uma so.
export interface Bairro { name: string; lat: number; lng: number }

export const BAIRROS: Bairro[] = [
  { name: 'AUGUSTA', lat: -23.553, lng: -46.656 },
  { name: 'VILA MADALENA', lat: -23.556, lng: -46.69 },
  { name: 'BARRA FUNDA', lat: -23.526, lng: -46.664 },
  { name: 'LAPA', lat: -23.523, lng: -46.705 },
  { name: 'ITAIM / V. OLÍMPIA', lat: -23.585, lng: -46.679 },
  { name: 'PINHEIROS', lat: -23.567, lng: -46.695 },
  { name: 'CENTRO', lat: -23.544, lng: -46.642 },
  { name: 'BEXIGA', lat: -23.558, lng: -46.645 },
  { name: 'VILA MARIANA', lat: -23.589, lng: -46.634 },
  { name: 'MOEMA', lat: -23.6, lng: -46.665 },
  { name: 'SANTANA', lat: -23.503, lng: -46.625 },
  { name: 'TATUAPÉ', lat: -23.54, lng: -46.576 },
  { name: 'BROOKLIN', lat: -23.61, lng: -46.69 },
  { name: 'PERDIZES / POMPEIA', lat: -23.532, lng: -46.682 },
  { name: 'LIBERDADE', lat: -23.559, lng: -46.635 },
  { name: 'SANTA CECÍLIA', lat: -23.5405, lng: -46.6535 },
  { name: 'BOM RETIRO', lat: -23.527, lng: -46.643 },
  { name: 'MOOCA', lat: -23.5555, lng: -46.5985 },
  { name: 'IPIRANGA', lat: -23.592, lng: -46.61 },
]

export const CLASSIFY_MAX_KM = 2

export function distanceKm(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const R = 6371
  const rad = (x: number) => (x * Math.PI) / 180
  const dLat = rad(bLat - aLat)
  const dLng = rad(bLng - aLng)
  const h = Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(aLat)) * Math.cos(rad(bLat)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

export function classify(lat: number, lng: number): string | null {
  let best: string | null = null
  let bestD = Infinity
  for (const b of BAIRROS) {
    const d = distanceKm(lat, lng, b.lat, b.lng)
    if (d < bestD) { bestD = d; best = b.name }
  }
  return bestD <= CLASSIFY_MAX_KM ? best : null
}
```

- [ ] **Step 4: Run tests**

Run: `cd web && npx vitest run src/data/bairros.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/data/bairros.ts web/src/data/bairros.test.ts
git commit -m "feat(web): bairros.ts — centroides das sementes + haversine + classify(lat,lng)"
```

---

### Task 5: Web — `data/vivacity.ts` (atividade IG + festas hoje)

**Files:**
- Create: `web/src/data/vivacity.ts`
- Test: `web/src/data/vivacity.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/data/vivacity.test.ts
import { describe, it, expect } from 'vitest'
import { igActivity, venueIdsWithEventToday, IG_ACTIVE_DAYS } from './vivacity'
import type { EventWithGeo } from './join'

const NOW = new Date(2026, 6, 10, 22, 0) // 10/07/2026 22h local

function evt(venueId: number | null, startsAt: string | null): EventWithGeo {
  return {
    id: Math.random(), name: 'x', starts_at: startsAt, ends_at: null,
    venue_id: venueId, status: 'scheduled', genre: null, ticket_url: null,
    flyer_url: null, confidence: 50, effective_confidence: 50,
    venueName: null, venueInstagram: null, venueIgLastPostAt: null,
    lat: null, lng: null, mappable: false,
  } as EventWithGeo
}

describe('igActivity', () => {
  it('post no mesmo dia local = hoje', () => {
    expect(igActivity(new Date(2026, 6, 10, 8, 0).toISOString(), NOW)).toBe('hoje')
  })
  it('post recente (<= 30d) = ativo', () => {
    expect(igActivity(new Date(2026, 5, 20).toISOString(), NOW)).toBe('ativo')
    expect(IG_ACTIVE_DAYS).toBe(30)
  })
  it('post velho (> 30d), null e lixo = null', () => {
    expect(igActivity(new Date(2026, 3, 1).toISOString(), NOW)).toBeNull()
    expect(igActivity(null, NOW)).toBeNull()
    expect(igActivity('nao-e-data', NOW)).toBeNull()
  })
})

describe('venueIdsWithEventToday', () => {
  it('so venues com starts_at no dia local de hoje', () => {
    const hoje = evt(1, new Date(2026, 6, 10, 23, 30).toISOString())
    const amanha = evt(2, new Date(2026, 6, 11, 1, 0).toISOString())
    const semData = evt(3, null)
    const semVenue = evt(null, new Date(2026, 6, 10, 23, 0).toISOString())
    const ids = venueIdsWithEventToday([hoje, amanha, semData, semVenue], NOW)
    expect(ids.has(1)).toBe(true)
    expect(ids.has(2)).toBe(false)
    expect(ids.has(3)).toBe(false)
    expect(ids.size).toBe(1)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/data/vivacity.test.ts`
Expected: FAIL (módulo não existe)

- [ ] **Step 3: Implement**

```ts
// web/src/data/vivacity.ts
import type { EventWithGeo } from './join'

export const IG_ACTIVE_DAYS = 30
export type IgActivity = 'hoje' | 'ativo' | null

function sameLocalDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
}

export function igActivity(iso: string | null, now: Date = new Date()): IgActivity {
  if (!iso) return null
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  if (sameLocalDay(d, now)) return 'hoje'
  const days = (now.getTime() - d.getTime()) / 86_400_000
  return days <= IG_ACTIVE_DAYS ? 'ativo' : null
}

export function venueIdsWithEventToday(events: EventWithGeo[], now: Date = new Date()): Set<number> {
  const out = new Set<number>()
  for (const e of events) {
    if (e.venue_id == null || !e.starts_at) continue
    const d = new Date(e.starts_at)
    if (!isNaN(d.getTime()) && sameLocalDay(d, now)) out.add(e.venue_id)
  }
  return out
}
```

- [ ] **Step 4: Run tests**

Run: `cd web && npx vitest run src/data/vivacity.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/data/vivacity.ts web/src/data/vivacity.test.ts
git commit -m "feat(web): vivacity.ts — igActivity (hoje/ativo/null) + venueIdsWithEventToday"
```

---

### Task 6: Web — reducer estendido (`filters/state.ts`)

**Files:**
- Modify: `web/src/filters/state.ts`, `web/src/filters/state.test.ts`, `web/src/tabs/FestasTab.tsx` (entrada `date` no TITLES)

Dimensões novas: `date` (preset 'date' + dia exato), `genres` multi **client-side** (substitui `genre` — a API deixa de receber `genre`), `bairro`, `nearMe` (mutuamente exclusivos), `extras` {ticket, flyer, igAtivo}, `clearAll`, `activeFilterCount`.

- [ ] **Step 1: Write the failing tests** — SUBSTITUA o conteúdo de `state.test.ts` pelos testes atuais adaptados + novos:

```ts
import { describe, it, expect } from 'vitest'
import { initialFilters, filterReducer, queryFromFilters, activeFilterCount } from './state'

describe('filters', () => {
  it('estado inicial', () => {
    expect(initialFilters).toEqual({
      preset: 'upcoming', date: null, genres: [], minConfidence: 0, includePast: false,
      bairro: null, nearMe: null, extras: { ticket: false, flyer: false, igAtivo: false },
    })
  })
  it('toggleGenre acumula e remove (multi)', () => {
    const a = filterReducer(initialFilters, { type: 'toggleGenre', genre: 'techno' })
    const b = filterReducer(a, { type: 'toggleGenre', genre: 'funk' })
    expect(b.genres).toEqual(['techno', 'funk'])
    expect(filterReducer(b, { type: 'toggleGenre', genre: 'techno' }).genres).toEqual(['funk'])
  })
  it('bairro e nearMe sao mutuamente exclusivos', () => {
    const comBairro = filterReducer(initialFilters, { type: 'setBairro', bairro: 'AUGUSTA' })
    const comGps = filterReducer(comBairro, { type: 'setNearMe', point: { lat: -23.55, lng: -46.66 } })
    expect(comGps.bairro).toBeNull()
    expect(comGps.nearMe).toEqual({ lat: -23.55, lng: -46.66 })
    expect(filterReducer(comGps, { type: 'setBairro', bairro: 'LAPA' }).nearMe).toBeNull()
  })
  it('toggleExtra liga/desliga sem afetar os irmaos', () => {
    const s = filterReducer(initialFilters, { type: 'toggleExtra', key: 'flyer' })
    expect(s.extras).toEqual({ ticket: false, flyer: true, igAtivo: false })
    expect(filterReducer(s, { type: 'toggleExtra', key: 'flyer' }).extras.flyer).toBe(false)
  })
  it('setDate seta preset=date; setPreset limpa a data', () => {
    const s = filterReducer(initialFilters, { type: 'setDate', date: '2026-07-18' })
    expect(s.preset).toBe('date')
    expect(s.date).toBe('2026-07-18')
    const volta = filterReducer(s, { type: 'setPreset', preset: 'today' })
    expect(volta.date).toBeNull()
  })
  it('clearAll volta ao inicial', () => {
    let s = filterReducer(initialFilters, { type: 'setBairro', bairro: 'AUGUSTA' })
    s = filterReducer(s, { type: 'toggleGenre', genre: 'techno' })
    expect(filterReducer(s, { type: 'clearAll' })).toEqual(initialFilters)
  })
  it('activeFilterCount conta dimensoes ativas', () => {
    expect(activeFilterCount(initialFilters)).toBe(0)
    let s = filterReducer(initialFilters, { type: 'toggleGenre', genre: 'techno' })
    s = filterReducer(s, { type: 'toggleGenre', genre: 'funk' })   // genres = 1 dimensao
    s = filterReducer(s, { type: 'setBairro', bairro: 'AUGUSTA' })
    s = filterReducer(s, { type: 'toggleExtra', key: 'ticket' })
    s = filterReducer(s, { type: 'setMinConfidence', value: 40 })
    expect(activeFilterCount(s)).toBe(4)
  })
})

describe('queryFromFilters', () => {
  it('genero NAO vai mais pra API (filtro client-side)', () => {
    const s = filterReducer(initialFilters, { type: 'toggleGenre', genre: 'techno' })
    expect(queryFromFilters({ ...s, minConfidence: 40 })).toEqual({ min_confidence: 40 })
  })
  it('preset date vira date_from=date_to', () => {
    const s = filterReducer(initialFilters, { type: 'setDate', date: '2026-07-18' })
    const q = queryFromFilters(s)
    expect(q.date_from).toBe('2026-07-18')
    expect(q.date_to).toBe('2026-07-18')
  })
  it('datas locais dos presets preservadas (regressao C-1)', () => {
    const evening = new Date(2026, 6, 4, 21, 0, 0)
    const hoje = queryFromFilters({ ...initialFilters, preset: 'today' }, evening)
    expect(hoje.date_from).toBe('2026-07-04')
    const wknd = queryFromFilters({ ...initialFilters, preset: 'weekend' }, evening)
    expect(wknd.date_from).toBe('2026-07-10')
    expect(wknd.date_to).toBe('2026-07-12')
    const amanha = queryFromFilters({ ...initialFilters, preset: 'tomorrow' }, evening)
    expect(amanha.date_from).toBe('2026-07-05')
    expect(queryFromFilters({ ...initialFilters, preset: 'all', includePast: true }).include_past).toBe(true)
  })
})
```

(O bloco `describe('preset tomorrow')` existente pode ser absorvido pelo teste de regressão acima.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/filters/state.test.ts`
Expected: FAIL (shape novo não existe)

- [ ] **Step 3: Implement** — `state.ts` completo:

```ts
import type { EventQuery } from '../api/client'

export type Preset = 'upcoming' | 'today' | 'tomorrow' | 'weekend' | 'date' | 'all'

export interface Extras { ticket: boolean; flyer: boolean; igAtivo: boolean }

export interface FilterState {
  preset: Preset
  date: string | null                       // YYYY-MM-DD quando preset='date'
  genres: string[]                          // multi, client-side
  minConfidence: number
  includePast: boolean
  bairro: string | null                     // exclusivo com nearMe
  nearMe: { lat: number; lng: number } | null
  extras: Extras
}

export const initialFilters: FilterState = {
  preset: 'upcoming', date: null, genres: [], minConfidence: 0, includePast: false,
  bairro: null, nearMe: null, extras: { ticket: false, flyer: false, igAtivo: false },
}

export type FilterAction =
  | { type: 'setPreset'; preset: Preset }
  | { type: 'setDate'; date: string }
  | { type: 'toggleGenre'; genre: string }
  | { type: 'setMinConfidence'; value: number }
  | { type: 'setIncludePast'; value: boolean }
  | { type: 'setBairro'; bairro: string | null }
  | { type: 'setNearMe'; point: { lat: number; lng: number } | null }
  | { type: 'toggleExtra'; key: keyof Extras }
  | { type: 'clearAll' }

export function filterReducer(state: FilterState, action: FilterAction): FilterState {
  switch (action.type) {
    case 'setPreset':
      return { ...state, preset: action.preset, date: null, includePast: action.preset === 'all' }
    case 'setDate':
      return { ...state, preset: 'date', date: action.date, includePast: false }
    case 'toggleGenre':
      return {
        ...state,
        genres: state.genres.includes(action.genre)
          ? state.genres.filter((g) => g !== action.genre)
          : [...state.genres, action.genre],
      }
    case 'setMinConfidence': return { ...state, minConfidence: action.value }
    case 'setIncludePast': return { ...state, includePast: action.value }
    case 'setBairro':
      return { ...state, bairro: action.bairro, nearMe: action.bairro ? null : state.nearMe }
    case 'setNearMe':
      return { ...state, nearMe: action.point, bairro: action.point ? null : state.bairro }
    case 'toggleExtra':
      return { ...state, extras: { ...state.extras, [action.key]: !state.extras[action.key] } }
    case 'clearAll': return initialFilters
  }
}

export function activeFilterCount(f: FilterState): number {
  let n = 0
  if (f.genres.length > 0) n++
  if (f.bairro) n++
  if (f.nearMe) n++
  if (f.extras.ticket) n++
  if (f.extras.flyer) n++
  if (f.extras.igAtivo) n++
  if (f.minConfidence > 0) n++
  return n
}

function isoDate(d: Date): string {
  // Dia do CALENDARIO LOCAL, nao UTC — app de vida noturna usado a noite:
  // toISOString() desloca +1 dia em fusos negativos (UTC-3) apos ~21h.
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function queryFromFilters(f: FilterState, now: Date = new Date()): EventQuery {
  const q: EventQuery = {}
  if (f.minConfidence > 0) q.min_confidence = f.minConfidence

  if (f.preset === 'today') {
    q.date_from = isoDate(now)
    q.date_to = isoDate(now)
  } else if (f.preset === 'tomorrow') {
    const t = new Date(now); t.setDate(now.getDate() + 1)
    q.date_from = isoDate(t)
    q.date_to = isoDate(t)
  } else if (f.preset === 'weekend') {
    const day = now.getDay()
    const toFri = (5 - day + 7) % 7
    const fri = new Date(now); fri.setDate(now.getDate() + toFri)
    const sun = new Date(fri); sun.setDate(fri.getDate() + 2)
    q.date_from = isoDate(fri)
    q.date_to = isoDate(sun)
  } else if (f.preset === 'date' && f.date) {
    q.date_from = f.date
    q.date_to = f.date
  } else if (f.preset === 'all') {
    q.include_past = true
  }
  return q
}
```

Em `FestasTab.tsx`, acrescente ao `TITLES`: `date: ['NESSE', 'DIA'],`

- [ ] **Step 4: Run tests + typecheck**

Run: `cd web && npx vitest run src/filters/state.test.ts && npx tsc -b`
Expected: state.test PASS. Se `FilterChips.test.tsx`/`FestasTab.test.tsx` quebrarem por referirem `genre`, ajuste as fixtures (spread de `initialFilters` resolve a maioria).

- [ ] **Step 5: Commit**

```bash
git add web/src/filters/state.ts web/src/filters/state.test.ts web/src/tabs/FestasTab.tsx
git commit -m "feat(web): reducer de filtros estendido — date, genres multi, bairro/nearMe, extras, contador"
```

---

### Task 7: Web — `filters/apply.ts` (filtros client-side + contagem viva)

**Files:**
- Create: `web/src/filters/apply.ts`
- Test: `web/src/filters/apply.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/filters/apply.test.ts
import { describe, it, expect } from 'vitest'
import { applyClientFilters, NEAR_ME_KM } from './apply'
import { initialFilters } from './state'
import type { EventWithGeo } from '../data/join'

const NOW = new Date(2026, 6, 10, 22, 0)

let seq = 0
function evt(over: Partial<EventWithGeo>): EventWithGeo {
  return {
    id: ++seq, name: 'x', starts_at: null, ends_at: null, venue_id: 1,
    status: 'scheduled', genre: null, ticket_url: null, flyer_url: null,
    confidence: 50, effective_confidence: 50, venueName: null,
    venueInstagram: null, venueIgLastPostAt: null,
    lat: null, lng: null, mappable: false, ...over,
  } as EventWithGeo
}

describe('applyClientFilters', () => {
  it('sem filtros ativos devolve tudo', () => {
    const evs = [evt({}), evt({ genre: 'techno' })]
    expect(applyClientFilters(evs, initialFilters, NOW)).toHaveLength(2)
  })
  it('genres multi: casa qualquer um; evento sem genero cai fora', () => {
    const evs = [evt({ genre: 'techno' }), evt({ genre: 'funk' }), evt({ genre: 'rock' }), evt({})]
    const f = { ...initialFilters, genres: ['techno', 'funk'] }
    expect(applyClientFilters(evs, f, NOW).map((e) => e.genre)).toEqual(['techno', 'funk'])
  })
  it('bairro classifica por lat/lng; sem geo cai fora', () => {
    const vilaMad = evt({ lat: -23.556, lng: -46.69, mappable: true })
    const tatuape = evt({ lat: -23.54, lng: -46.576, mappable: true })
    const semGeo = evt({})
    const f = { ...initialFilters, bairro: 'VILA MADALENA' }
    expect(applyClientFilters([vilaMad, tatuape, semGeo], f, NOW)).toEqual([vilaMad])
  })
  it('nearMe: raio de NEAR_ME_KM', () => {
    const perto = evt({ lat: -23.556, lng: -46.69, mappable: true })
    const longe = evt({ lat: -23.54, lng: -46.576, mappable: true }) // Tatuape, ~12km
    const f = { ...initialFilters, nearMe: { lat: -23.556, lng: -46.692 } }
    expect(applyClientFilters([perto, longe], f, NOW)).toEqual([perto])
    expect(NEAR_ME_KM).toBe(3)
  })
  it('extras: ticket, flyer e igAtivo', () => {
    const full = evt({ ticket_url: 't', flyer_url: 'f', venueIgLastPostAt: new Date(2026, 6, 9).toISOString() })
    const pelado = evt({})
    const fT = { ...initialFilters, extras: { ticket: true, flyer: false, igAtivo: false } }
    const fF = { ...initialFilters, extras: { ticket: false, flyer: true, igAtivo: false } }
    const fIG = { ...initialFilters, extras: { ticket: false, flyer: false, igAtivo: true } }
    expect(applyClientFilters([full, pelado], fT, NOW)).toEqual([full])
    expect(applyClientFilters([full, pelado], fF, NOW)).toEqual([full])
    expect(applyClientFilters([full, pelado], fIG, NOW)).toEqual([full])
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/filters/apply.test.ts`
Expected: FAIL (módulo não existe)

- [ ] **Step 3: Implement**

```ts
// web/src/filters/apply.ts
import type { EventWithGeo } from '../data/join'
import type { FilterState } from './state'
import { classify, distanceKm } from '../data/bairros'
import { igActivity } from '../data/vivacity'

export const NEAR_ME_KM = 3

export function applyClientFilters(
  events: EventWithGeo[], f: FilterState, now: Date = new Date(),
): EventWithGeo[] {
  return events.filter((e) => {
    if (f.genres.length > 0 && (!e.genre || !f.genres.includes(e.genre))) return false
    if (f.bairro && (!e.mappable || classify(e.lat!, e.lng!) !== f.bairro)) return false
    if (f.nearMe &&
        (!e.mappable || distanceKm(f.nearMe.lat, f.nearMe.lng, e.lat!, e.lng!) > NEAR_ME_KM)) return false
    if (f.extras.ticket && !e.ticket_url) return false
    if (f.extras.flyer && !e.flyer_url) return false
    if (f.extras.igAtivo && igActivity(e.venueIgLastPostAt, now) === null) return false
    return true
  })
}
```

- [ ] **Step 4: Run tests**

Run: `cd web && npx vitest run src/filters/apply.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/filters/apply.ts web/src/filters/apply.test.ts
git commit -m "feat(web): applyClientFilters — genres/bairro/nearMe/extras sobre o array joinado"
```

---

### Task 8: Web — `FilterChips` final (≡ FILTROS com contador)

**Files:**
- Modify: `web/src/components/FilterChips.tsx`, `web/src/components/FilterChips.test.tsx`, `web/src/tabs/FestasTab.tsx` (repassa props novas)

- [ ] **Step 1: Write the failing tests** — acrescente ao `FilterChips.test.tsx`:

```ts
it('botao FILTROS abre o sheet e mostra contador quando ha filtro ativo', async () => {
  const onOpenSheet = vi.fn()
  render(<FilterChips filters={initialFilters} dispatch={() => {}}
                      activeCount={2} onOpenSheet={onOpenSheet} />)
  const btn = screen.getByRole('button', { name: /FILTROS/ })
  expect(btn).toHaveTextContent('≡ FILTROS ·2')
  await userEvent.click(btn)
  expect(onOpenSheet).toHaveBeenCalled()
})
it('sem filtro ativo o botao nao tem contador', () => {
  render(<FilterChips filters={initialFilters} dispatch={() => {}}
                      activeCount={0} onOpenSheet={() => {}} />)
  expect(screen.getByRole('button', { name: /FILTROS/ })).toHaveTextContent('≡ FILTROS')
  expect(screen.queryByText(/·/)).toBeNull()
})
```

Os testes existentes ganham as props novas (`activeCount={0} onOpenSheet={() => {}}`).

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/components/FilterChips.test.tsx`
Expected: FAIL (props não existem)

- [ ] **Step 3: Implement** — `FilterChips.tsx`:

```tsx
import type { Dispatch } from 'react'
import type { FilterAction, FilterState, Preset } from '../filters/state'

const PRESETS: { key: Preset; label: string }[] = [
  { key: 'upcoming', label: 'PRÓXIMAS' },
  { key: 'today', label: 'HOJE' },
  { key: 'tomorrow', label: 'AMANHÃ' },
  { key: 'weekend', label: 'FDS' },
  { key: 'all', label: 'TUDO' },
]

export function FilterChips({ filters, dispatch, activeCount, onOpenSheet }: {
  filters: FilterState; dispatch: Dispatch<FilterAction>
  activeCount: number; onOpenSheet: () => void
}) {
  return (
    <div style={{ display: 'flex', gap: 5, padding: '6px 12px', overflowX: 'auto' }}>
      {PRESETS.map((p) => (
        <button key={p.key} className={`chip${filters.preset === p.key ? ' on' : ''}`}
                onClick={() => dispatch({ type: 'setPreset', preset: p.key })}>
          {p.label}
        </button>
      ))}
      <button className={`chip${activeCount > 0 ? ' grn' : ''}`} onClick={onOpenSheet}>
        {`≡ FILTROS${activeCount > 0 ? ` ·${activeCount}` : ''}`}
      </button>
    </div>
  )
}
```

Em `FestasTab.tsx`: props ganham `activeCount: number; onOpenSheet: () => void` e repassam pro `<FilterChips>`. Ajuste `FestasTab.test.tsx` (props novas nos renders).

- [ ] **Step 4: Run tests + typecheck**

Run: `cd web && npx vitest run src/components/FilterChips.test.tsx src/tabs/FestasTab.test.tsx && npx tsc -b`
Expected: PASS — `App.tsx` ainda não passa as props → se o tsc reclamar, adicione em `App.tsx` provisoriamente `activeCount={0} onOpenSheet={() => {}}` no `<FestasTab>` (a Task 10 liga de verdade).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/FilterChips.tsx web/src/components/FilterChips.test.tsx web/src/tabs/FestasTab.tsx web/src/tabs/FestasTab.test.tsx web/src/App.tsx
git commit -m "feat(web): FilterChips ganha botao ≡ FILTROS com contador de dimensoes ativas"
```

---

### Task 9: Web — `FilterSheet` (sheet avançado com botão-resultado vivo)

**Files:**
- Create: `web/src/components/FilterSheet.tsx`
- Test: `web/src/components/FilterSheet.test.tsx`

O sheet edita o reducer AO VIVO (sem draft): cada chip dispara `dispatch`; `count` (prop) é o tamanho da lista já filtrada; "VER N FESTAS →" fecha; "LIMPAR" dispara `clearAll`. GPS negado → chip PERTO DE MIM desabilita silenciosamente (spec §7).

- [ ] **Step 1: Write the failing tests**

```tsx
// web/src/components/FilterSheet.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterSheet } from './FilterSheet'
import { initialFilters } from '../filters/state'

const base = {
  filters: initialFilters, dispatch: () => {}, count: 12,
  genreOptions: ['funk', 'techno'], onClose: () => {},
}

describe('FilterSheet', () => {
  it('renderiza as secoes e o botao-resultado vivo', () => {
    render(<FilterSheet {...base} />)
    for (const sec of ['QUANDO', 'ONDE', 'SOM', 'EXTRAS', 'CONFIANÇA']) {
      expect(screen.getByText(sec)).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'VER 12 FESTAS →' })).toBeInTheDocument()
  })
  it('toggla genero e extra via dispatch', async () => {
    const dispatch = vi.fn()
    render(<FilterSheet {...base} dispatch={dispatch} />)
    await userEvent.click(screen.getByRole('button', { name: 'TECHNO' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'toggleGenre', genre: 'techno' })
    await userEvent.click(screen.getByRole('button', { name: 'COM FLYER' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'toggleExtra', key: 'flyer' })
  })
  it('seleciona bairro e confianca', async () => {
    const dispatch = vi.fn()
    render(<FilterSheet {...base} dispatch={dispatch} />)
    await userEvent.click(screen.getByRole('button', { name: 'AUGUSTA' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'setBairro', bairro: 'AUGUSTA' })
    await userEvent.click(screen.getByRole('button', { name: '70+' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'setMinConfidence', value: 70 })
  })
  it('PERTO DE MIM pede geolocation e dispara setNearMe', async () => {
    const dispatch = vi.fn()
    const getCurrentPosition = vi.fn((ok: PositionCallback) =>
      ok({ coords: { latitude: -23.55, longitude: -46.66 } } as GeolocationPosition))
    vi.stubGlobal('navigator', { ...navigator, geolocation: { getCurrentPosition } })
    render(<FilterSheet {...base} dispatch={dispatch} />)
    await userEvent.click(screen.getByRole('button', { name: /PERTO DE MIM/ }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'setNearMe', point: { lat: -23.55, lng: -46.66 } })
    vi.unstubAllGlobals()
  })
  it('VER fecha; LIMPAR dispara clearAll', async () => {
    const onClose = vi.fn()
    const dispatch = vi.fn()
    render(<FilterSheet {...base} onClose={onClose} dispatch={dispatch} />)
    await userEvent.click(screen.getByRole('button', { name: 'VER 12 FESTAS →' }))
    expect(onClose).toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'LIMPAR' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'clearAll' })
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/components/FilterSheet.test.tsx`
Expected: FAIL (módulo não existe)

- [ ] **Step 3: Implement**

```tsx
// web/src/components/FilterSheet.tsx
import { useState } from 'react'
import type { Dispatch } from 'react'
import type { FilterAction, FilterState, Extras } from '../filters/state'
import { BAIRROS } from '../data/bairros'

const EXTRAS: { key: keyof Extras; label: string }[] = [
  { key: 'ticket', label: 'COM TICKET' },
  { key: 'flyer', label: 'COM FLYER' },
  { key: 'igAtivo', label: 'IG ATIVO' },
]
const CONFS = [{ v: 0, label: 'TODAS' }, { v: 40, label: '40+' }, { v: 70, label: '70+' }]

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ padding: '10px 12px 2px' }}>
      <div className="label" style={{ marginBottom: 7 }}>{title}</div>
      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>{children}</div>
    </div>
  )
}

export function FilterSheet({ filters, dispatch, count, genreOptions, onClose }: {
  filters: FilterState; dispatch: Dispatch<FilterAction>
  count: number; genreOptions: string[]; onClose: () => void
}) {
  const [gpsDenied, setGpsDenied] = useState(false)

  const nearMeClick = () => {
    if (filters.nearMe) { dispatch({ type: 'setNearMe', point: null }); return }
    navigator.geolocation?.getCurrentPosition(
      (pos) => dispatch({ type: 'setNearMe',
                          point: { lat: pos.coords.latitude, lng: pos.coords.longitude } }),
      () => setGpsDenied(true),  // negado: chip apaga, resto intacto (spec §7)
    )
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 40, background: 'rgba(0,0,0,0.65)' }}
         onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           style={{ position: 'absolute', left: 0, right: 0, bottom: 0, maxHeight: '88dvh',
                    display: 'flex', flexDirection: 'column', background: 'var(--black)',
                    borderTop: '3px solid var(--pink)', animation: 'b-slide-up 0.18s ease-out' }}>
        <div style={{ overflowY: 'auto', paddingBottom: 8 }}>
          <Section title="QUANDO">
            {([['upcoming', 'PRÓXIMAS'], ['today', 'HOJE'], ['tomorrow', 'AMANHÃ'],
               ['weekend', 'FDS'], ['all', 'TUDO']] as const).map(([key, label]) => (
              <button key={key} className={`chip${filters.preset === key ? ' on' : ''}`}
                      onClick={() => dispatch({ type: 'setPreset', preset: key })}>{label}</button>
            ))}
            <input type="date" value={filters.date ?? ''} aria-label="DATA"
                   onChange={(e) => e.target.value && dispatch({ type: 'setDate', date: e.target.value })}
                   className={`chip${filters.preset === 'date' ? ' on' : ''}`}
                   style={{ colorScheme: 'dark' }} />
          </Section>
          <Section title="ONDE">
            <button className={`chip grn${filters.nearMe ? ' on' : ''}`}
                    disabled={gpsDenied} style={gpsDenied ? { opacity: 0.35 } : undefined}
                    onClick={nearMeClick}>⌖ PERTO DE MIM</button>
            {BAIRROS.map((b) => (
              <button key={b.name} className={`chip${filters.bairro === b.name ? ' on' : ''}`}
                      onClick={() => dispatch({ type: 'setBairro',
                                                bairro: filters.bairro === b.name ? null : b.name })}>
                {b.name}
              </button>
            ))}
          </Section>
          <Section title="SOM">
            {genreOptions.length === 0 && (
              <span className="label" style={{ fontWeight: 700 }}>SEM GÊNEROS NOS RESULTADOS</span>
            )}
            {genreOptions.map((g) => (
              <button key={g} className={`chip${filters.genres.includes(g) ? ' on' : ''}`}
                      onClick={() => dispatch({ type: 'toggleGenre', genre: g })}>
                {g.toUpperCase()}
              </button>
            ))}
          </Section>
          <Section title="EXTRAS">
            {EXTRAS.map((x) => (
              <button key={x.key} className={`chip${filters.extras[x.key] ? ' on' : ''}`}
                      onClick={() => dispatch({ type: 'toggleExtra', key: x.key })}>{x.label}</button>
            ))}
          </Section>
          <Section title="CONFIANÇA">
            {CONFS.map((c) => (
              <button key={c.v} className={`chip${filters.minConfidence === c.v ? ' on' : ''}`}
                      onClick={() => dispatch({ type: 'setMinConfidence', value: c.v })}>{c.label}</button>
            ))}
          </Section>
        </div>
        <div style={{ display: 'flex', gap: 8, padding: 10, borderTop: '1px solid var(--line)' }}>
          <button className="b-btn" style={{ width: 110 }}
                  onClick={() => dispatch({ type: 'clearAll' })}>LIMPAR</button>
          <button className="b-btn primary" style={{ flex: 1 }}
                  onClick={onClose}>{`VER ${count} FESTAS →`}</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

Run: `cd web && npx vitest run src/components/FilterSheet.test.tsx && npx tsc -b`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/components/FilterSheet.tsx web/src/components/FilterSheet.test.tsx
git commit -m "feat(web): FilterSheet — QUANDO/ONDE/SOM/EXTRAS/CONFIANCA com VER N FESTAS vivo"
```

---

### Task 10: Web — wiring no `App.tsx` (filtro client + sheet único)

**Files:**
- Modify: `web/src/App.tsx`, `web/src/tabs/FestasTab.tsx` (se necessário)

Sem teste unitário próprio (App é verificado por `tsc -b` + suíte + smoke — padrão do projeto).

- [ ] **Step 1: Implement** — em `App.tsx`:

```tsx
import { useEffect, useMemo, useReducer, useState } from 'react'
import { activeFilterCount, filterReducer, initialFilters, queryFromFilters } from './filters/state'
import { applyClientFilters } from './filters/apply'
import { FilterSheet } from './components/FilterSheet'
```

Dentro de `App()`:

```tsx
  const [sheetOpen, setSheetOpen] = useState(false)
  // filtros client-side sobre o array joinado; a API so recebe datas/confianca
  const filtered = useMemo(() => applyClientFilters(events, filters), [events, filters])
  const genreOptions = useMemo(
    () => [...new Set(events.map((e) => e.genre).filter((g): g is string => !!g))].sort(),
    [events])
  const activeCount = activeFilterCount(filters)
```

- `festas` passa a receber `events={filtered}` + `activeCount={activeCount}` + `onOpenSheet={() => setSheetOpen(true)}`.
- Contadores de header/desktop usam `filtered.length`.
- `MapView` (por enquanto) recebe `events={filtered}` — a Task 12 troca pelo MapaTab.
- Renderize o sheet UMA vez, nos dois layouts (desktop e mobile), junto do `EventDetail`:

```tsx
      {sheetOpen && (
        <FilterSheet filters={filters} dispatch={dispatch} count={filtered.length}
                     genreOptions={genreOptions} onClose={() => setSheetOpen(false)} />
      )}
```

(Confira o z-index do `EventDetail`; o sheet usa 40 e deve ficar ACIMA da tabbar (30) e abaixo/acima do detail conforme o caso — detail abre por cima, então detail deve ter z ≥ 50; ajuste o do detail se preciso.)

- [ ] **Step 2: Verify**

Run: `cd web && npx tsc -b && npx vitest run`
Expected: typecheck limpo, suíte inteira PASS

- [ ] **Step 3: Commit**

```bash
git add web/src/App.tsx web/src/tabs/FestasTab.tsx
git commit -m "feat(web): App liga filtros client-side + FilterSheet unico nos dois layouts"
```

---

### Task 11: Web — gaveta (helper puro + componente `Drawer`)

**Files:**
- Create: `web/src/components/drawerSnap.ts`, `web/src/components/Drawer.tsx`
- Test: `web/src/components/drawerSnap.test.ts`, `web/src/components/Drawer.test.tsx`

- [ ] **Step 1: Write the failing tests (helper)**

```ts
// web/src/components/drawerSnap.test.ts
import { describe, it, expect } from 'vitest'
import { drawerHeight, snapTo, CLOSED_PX } from './drawerSnap'

describe('drawerSnap', () => {
  it('alturas dos 3 estados', () => {
    expect(drawerHeight('closed', 800)).toBe(CLOSED_PX)
    expect(drawerHeight('half', 800)).toBe(360)   // 45%
    expect(drawerHeight('full', 800)).toBe(680)   // 85%
  })
  it('snapTo escolhe o estado mais proximo', () => {
    expect(snapTo(70, 800)).toBe('closed')
    expect(snapTo(300, 800)).toBe('half')
    expect(snapTo(500, 800)).toBe('half')
    expect(snapTo(600, 800)).toBe('full')
    expect(snapTo(9999, 800)).toBe('full')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/components/drawerSnap.test.ts`
Expected: FAIL (módulo não existe)

- [ ] **Step 3: Implement helper**

```ts
// web/src/components/drawerSnap.ts
export type DrawerState = 'closed' | 'half' | 'full'

export const CLOSED_PX = 64
const HALF = 0.45
const FULL = 0.85

export function drawerHeight(s: DrawerState, viewportH: number): number {
  if (s === 'closed') return CLOSED_PX
  return Math.round(viewportH * (s === 'half' ? HALF : FULL))
}

export function snapTo(px: number, viewportH: number): DrawerState {
  const states: DrawerState[] = ['closed', 'half', 'full']
  let best: DrawerState = 'closed'
  let bestD = Infinity
  for (const s of states) {
    const d = Math.abs(drawerHeight(s, viewportH) - px)
    if (d < bestD) { bestD = d; best = s }
  }
  return best
}
```

- [ ] **Step 4: Component test**

```tsx
// web/src/components/Drawer.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Drawer } from './Drawer'

describe('Drawer', () => {
  it('renderiza label e children; tap no handle alterna closed->half', async () => {
    const onState = vi.fn()
    render(
      <Drawer state="closed" onState={onState} label="12 FESTAS">
        <div>conteudo da lista</div>
      </Drawer>,
    )
    expect(screen.getByText('12 FESTAS')).toBeInTheDocument()
    expect(screen.getByText('conteudo da lista')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /12 FESTAS/ }))
    expect(onState).toHaveBeenCalledWith('half')
  })
  it('tap com gaveta aberta fecha', async () => {
    const onState = vi.fn()
    render(<Drawer state="half" onState={onState} label="X"><div /></Drawer>)
    await userEvent.click(screen.getByRole('button', { name: /X/ }))
    expect(onState).toHaveBeenCalledWith('closed')
  })
})
```

- [ ] **Step 5: Implement component**

```tsx
// web/src/components/Drawer.tsx
import { useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { CLOSED_PX, drawerHeight, snapTo, type DrawerState } from './drawerSnap'

const HANDLE_PX = 36

// Gaveta 3 estados (spec §7): discretos, transform/transition, SEM fisica.
// Drag so no handle (touch-action none) — o conteudo rola normal.
export function Drawer({ state, onState, bottom = 44, label, children }: {
  state: DrawerState; onState: (s: DrawerState) => void
  bottom?: number; label: string; children: ReactNode
}) {
  const [dragPx, setDragPx] = useState<number | null>(null)
  const start = useRef<{ y: number; h: number; moved: boolean } | null>(null)
  const vh = () => window.innerHeight - bottom
  const h = dragPx ?? drawerHeight(state, vh())

  const onPointerDown = (e: React.PointerEvent) => {
    ;(e.target as Element).setPointerCapture?.(e.pointerId)
    start.current = { y: e.clientY, h, moved: false }
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (!start.current) return
    const next = start.current.h + (start.current.y - e.clientY)
    if (Math.abs(e.clientY - start.current.y) > 5) start.current.moved = true
    setDragPx(Math.min(Math.max(next, CLOSED_PX), Math.round(vh() * 0.9)))
  }
  const onPointerUp = () => {
    if (!start.current) return
    if (start.current.moved && dragPx != null) onState(snapTo(dragPx, vh()))
    else onState(state === 'closed' ? 'half' : 'closed')  // tap alterna
    start.current = null
    setDragPx(null)
  }

  return (
    <div style={{ position: 'fixed', left: 0, right: 0, bottom, height: h, zIndex: 20,
                  background: 'var(--black)', borderTop: '3px solid var(--pink)',
                  transition: dragPx == null ? 'height 0.18s ease-out' : 'none',
                  display: 'flex', flexDirection: 'column' }}>
      <button aria-label={label}
              onPointerDown={onPointerDown} onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              style={{ height: HANDLE_PX, flex: 'none', touchAction: 'none',
                       background: 'none', border: 'none', cursor: 'grab',
                       display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
        <span style={{ width: 44, height: 4, background: 'var(--pink)' }} />
        <span className="label" style={{ color: 'var(--text)' }}>{label}</span>
      </button>
      <div style={{ overflowY: 'auto', flex: 1,
                    visibility: state === 'closed' && dragPx == null ? 'hidden' : 'visible' }}>
        {children}
      </div>
    </div>
  )
}
```

(Nota: `userEvent.click` dispara pointerdown/up sem move → cai no ramo "tap alterna" — é o que o teste cobre. jsdom não tem `setPointerCapture`, por isso o `?.`.)

- [ ] **Step 6: Run tests**

Run: `cd web && npx vitest run src/components/drawerSnap.test.ts src/components/Drawer.test.tsx && npx tsc -b`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add web/src/components/drawerSnap.ts web/src/components/drawerSnap.test.ts web/src/components/Drawer.tsx web/src/components/Drawer.test.tsx
git commit -m "feat(web): Drawer 3 estados com pointer events + helper puro de snap"
```

---

### Task 12: Web — `MapaTab` (CAMADAS + gaveta + chips) e wiring

**Files:**
- Create: `web/src/tabs/MapaTab.tsx`
- Test: `web/src/tabs/MapaTab.test.tsx` (com `vi.mock` do MapView — canvas GL não roda em jsdom)
- Modify: `web/src/App.tsx`

`MapView` NÃO muda: camada FESTAS desligada = `events={[]}`; LOCAIS = `showVenues`; SÓ COM FESTA HOJE filtra o array `venues`.

- [ ] **Step 1: Write the failing tests**

```tsx
// web/src/tabs/MapaTab.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { EventWithGeo } from '../data/join'
import type { VenueOut } from '../api/types'

const mapProps = vi.fn()
vi.mock('../map/MapView', () => ({
  MapView: (props: Record<string, unknown>) => { mapProps(props); return <div data-testid="map-stub" /> },
}))

import { MapaTab, visibleVenues } from './MapaTab'
import { initialFilters } from '../filters/state'

const NOW = new Date(2026, 6, 10, 22, 0)

function venue(id: number): VenueOut {
  return { id, name: `V${id}`, category: null, lat: -23.55, lng: -46.66, address: null,
           instagram: null, website: null, status: 'active', confidence: 50,
           effective_confidence: 50, is_monitored: false,
           ig_last_post_at: null, places_verified: false }
}
function evt(id: number, venueId: number, startsAt: string): EventWithGeo {
  return { id, name: `E${id}`, starts_at: startsAt, ends_at: null, venue_id: venueId,
           status: 'scheduled', genre: null, ticket_url: null, flyer_url: null,
           confidence: 50, effective_confidence: 50, venueName: null, venueInstagram: null,
           venueIgLastPostAt: null, lat: -23.55, lng: -46.66, mappable: true } as EventWithGeo
}

describe('visibleVenues', () => {
  it('hojeOnly filtra para venues com festa no dia local', () => {
    const evs = [evt(1, 10, new Date(2026, 6, 10, 23, 0).toISOString()),
                 evt(2, 20, new Date(2026, 6, 12, 23, 0).toISOString())]
    const vns = [venue(10), venue(20), venue(30)]
    expect(visibleVenues(vns, evs, { festas: true, locais: true, hojeOnly: false }, NOW)).toHaveLength(3)
    expect(visibleVenues(vns, evs, { festas: true, locais: true, hojeOnly: true }, NOW)
      .map((v) => v.id)).toEqual([10])
  })
})

describe('MapaTab', () => {
  const base = {
    events: [evt(1, 10, new Date(2026, 6, 10, 23, 0).toISOString())],
    venues: [venue(10)], filters: initialFilters, dispatch: () => {},
    selectedId: null, onSelect: () => {}, onOpenSheet: () => {}, activeCount: 0,
    withDrawer: true,
  }
  it('desligar FESTAS zera os events do MapView', async () => {
    render(<MapaTab {...base} />)
    await userEvent.click(screen.getByRole('button', { name: 'CAMADAS' }))
    await userEvent.click(screen.getByRole('button', { name: '◆ FESTAS' }))
    const last = mapProps.mock.calls.at(-1)![0] as { events: unknown[] }
    expect(last.events).toHaveLength(0)
  })
  it('desligar LOCAIS derruba showVenues', async () => {
    render(<MapaTab {...base} />)
    await userEvent.click(screen.getByRole('button', { name: 'CAMADAS' }))
    await userEvent.click(screen.getByRole('button', { name: '■ LOCAIS' }))
    const last = mapProps.mock.calls.at(-1)![0] as { showVenues: boolean }
    expect(last.showVenues).toBe(false)
  })
  it('com withDrawer renderiza a gaveta com a contagem', () => {
    render(<MapaTab {...base} />)
    expect(screen.getByText(/1 FESTAS NA ÁREA/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/tabs/MapaTab.test.tsx`
Expected: FAIL (módulo não existe)

- [ ] **Step 3: Implement**

```tsx
// web/src/tabs/MapaTab.tsx
import { useState } from 'react'
import type { Dispatch } from 'react'
import { MapView } from '../map/MapView'
import { Drawer } from '../components/Drawer'
import type { DrawerState } from '../components/drawerSnap'
import { EventCard } from '../components/EventCard'
import { FilterChips } from '../components/FilterChips'
import { venueIdsWithEventToday } from '../data/vivacity'
import type { EventWithGeo } from '../data/join'
import type { VenueOut } from '../api/types'
import type { FilterAction, FilterState } from '../filters/state'

export interface Layers { festas: boolean; locais: boolean; hojeOnly: boolean }

export function visibleVenues(
  venues: VenueOut[], events: EventWithGeo[], layers: Layers, now: Date = new Date(),
): VenueOut[] {
  if (!layers.hojeOnly) return venues
  const ids = venueIdsWithEventToday(events, now)
  return venues.filter((v) => ids.has(v.id))
}

const LAYER_DEFS: { key: keyof Layers; label: string }[] = [
  { key: 'festas', label: '◆ FESTAS' },
  { key: 'locais', label: '■ LOCAIS' },
  { key: 'hojeOnly', label: '□ SÓ COM FESTA HOJE' },
]

export function MapaTab({ events, venues, filters, dispatch, selectedId, onSelect,
                          onOpenSheet, activeCount, withDrawer }: {
  events: EventWithGeo[]; venues: VenueOut[]
  filters: FilterState; dispatch: Dispatch<FilterAction>
  selectedId: number | null; onSelect: (id: number) => void
  onOpenSheet: () => void; activeCount: number; withDrawer: boolean
}) {
  const [layers, setLayers] = useState<Layers>({ festas: true, locais: true, hojeOnly: false })
  const [panel, setPanel] = useState(false)
  const [drawer, setDrawer] = useState<DrawerState>('closed')

  return (
    <div style={{ position: 'relative', height: '100%' }}>
      <MapView events={layers.festas ? events : []}
               venues={visibleVenues(venues, events, layers)}
               selectedId={selectedId} onSelect={onSelect} showVenues={layers.locais} />

      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, zIndex: 10,
                    background: 'rgba(0,0,0,0.55)' }}>
        <FilterChips filters={filters} dispatch={dispatch}
                     activeCount={activeCount} onOpenSheet={onOpenSheet} />
      </div>

      <div style={{ position: 'absolute', top: 44, right: 8, zIndex: 10,
                    display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 5 }}>
        <button className={`chip${panel ? ' on' : ''}`} onClick={() => setPanel((p) => !p)}>
          CAMADAS
        </button>
        {panel && LAYER_DEFS.map((l) => (
          <button key={l.key} className={`chip${layers[l.key] ? ' on' : ''}`}
                  onClick={() => setLayers((s) => ({ ...s, [l.key]: !s[l.key] }))}>
            {l.label}
          </button>
        ))}
      </div>

      {withDrawer && (
        <Drawer state={drawer} onState={setDrawer} label={`${events.length} FESTAS NA ÁREA`}>
          {events.map((e) => (
            <EventCard key={e.id} event={e} variant="row"
                       onOpen={(ev) => onSelect(ev.id)} />
          ))}
          {events.length === 0 && <div className="empty">Nada com esses filtros.</div>}
        </Drawer>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Wire no `App.tsx`** — troque o elemento `mapa`:

```tsx
  const mapa = (
    <MapaTab events={filtered} venues={venues} filters={filters} dispatch={dispatch}
             selectedId={selectedId}
             onSelect={(id) => { const e = events.find((x) => x.id === id); if (e) openEvent(e) }}
             onOpenSheet={() => setSheetOpen(true)} activeCount={activeCount}
             withDrawer={!isDesktop} />
  )
```

(remova o import/uso direto de `MapView` no App; `showVenues`/`useState(true)` do App morre — a camada agora é do MapaTab).

- [ ] **Step 5: Run tests + typecheck**

Run: `cd web && npx vitest run && npx tsc -b`
Expected: PASS (suíte inteira)

- [ ] **Step 6: Commit**

```bash
git add web/src/tabs/MapaTab.tsx web/src/tabs/MapaTab.test.tsx web/src/App.tsx
git commit -m "feat(web): MapaTab — CAMADAS (festas/locais/so-com-festa-hoje) + gaveta + chips no mapa"
```

---

### Task 13: Web — `VenueCard` + `LocaisTab` (diretório vivo)

**Files:**
- Create: `web/src/components/VenueCard.tsx`, `web/src/tabs/LocaisTab.tsx`
- Test: `web/src/components/VenueCard.test.tsx`, `web/src/tabs/LocaisTab.test.tsx`
- Modify: `web/src/App.tsx` (substitui o placeholder)

Card expande INLINE (accordion — sem sheet novo): expandido mostra endereço, próximas festas (clicáveis → EventDetail) e chips IG/SITE/MAPA.

- [ ] **Step 1: Write the failing tests**

```tsx
// web/src/components/VenueCard.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { VenueCard } from './VenueCard'
import type { VenueOut } from '../api/types'
import type { EventWithGeo } from '../data/join'

const NOW = new Date(2026, 6, 10, 22, 0)

const base: VenueOut = {
  id: 1, name: 'D-Edge', category: 'nightclub', lat: -23.52, lng: -46.66,
  address: 'Al. Olga 170', instagram: 'dedgeclub', website: 'https://d-edge.com.br',
  status: 'active', confidence: 80, effective_confidence: 80, is_monitored: true,
  ig_last_post_at: null, places_verified: false,
}
function evt(name: string): EventWithGeo {
  return { id: 9, name, starts_at: '2026-07-11T02:00:00Z', ends_at: null, venue_id: 1,
           status: 'scheduled', genre: null, ticket_url: null, flyer_url: null,
           confidence: 50, effective_confidence: 50, venueName: 'D-Edge', venueInstagram: null,
           venueIgLastPostAt: null, lat: -23.52, lng: -46.66, mappable: true } as EventWithGeo
}

describe('VenueCard badges', () => {
  it('✓ VERIFICADO quando places_verified', () => {
    render(<VenueCard venue={{ ...base, places_verified: true }} upcoming={[]}
                      expanded={false} onToggle={() => {}} onOpenEvent={() => {}} now={NOW} />)
    expect(screen.getByText('✓ VERIFICADO')).toBeInTheDocument()
  })
  it('IG HOJE / IG ATIVO conforme ig_last_post_at', () => {
    const { rerender } = render(
      <VenueCard venue={{ ...base, ig_last_post_at: new Date(2026, 6, 10, 9).toISOString() }}
                 upcoming={[]} expanded={false} onToggle={() => {}} onOpenEvent={() => {}} now={NOW} />)
    expect(screen.getByText('IG HOJE')).toBeInTheDocument()
    rerender(
      <VenueCard venue={{ ...base, ig_last_post_at: new Date(2026, 6, 1).toISOString() }}
                 upcoming={[]} expanded={false} onToggle={() => {}} onOpenEvent={() => {}} now={NOW} />)
    expect(screen.getByText('IG ATIVO')).toBeInTheDocument()
  })
  it('contagem de festas futuras', () => {
    render(<VenueCard venue={base} upcoming={[evt('Gop Tun')]} expanded={false}
                      onToggle={() => {}} onOpenEvent={() => {}} now={NOW} />)
    expect(screen.getByText('1 FESTA')).toBeInTheDocument()
  })
  it('expandido mostra endereco, festas clicaveis e links', async () => {
    const onOpenEvent = vi.fn()
    render(<VenueCard venue={base} upcoming={[evt('Gop Tun')]} expanded={true}
                      onToggle={() => {}} onOpenEvent={onOpenEvent} now={NOW} />)
    expect(screen.getByText('Al. Olga 170')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Gop Tun'))
    expect(onOpenEvent).toHaveBeenCalled()
    expect(screen.getByRole('link', { name: 'IG' })).toHaveAttribute(
      'href', 'https://instagram.com/dedgeclub')
    expect(screen.getByRole('link', { name: 'MAPA' })).toHaveAttribute(
      'href', expect.stringContaining('maps.google.com'))
  })
})
```

```tsx
// web/src/tabs/LocaisTab.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LocaisTab, filterVenues, normalize } from './LocaisTab'
import type { VenueOut } from '../api/types'

function venue(id: number, name: string, address: string | null = null): VenueOut {
  return { id, name, category: 'nightclub', lat: -23.55, lng: -46.66, address,
           instagram: null, website: null, status: 'active', confidence: 50,
           effective_confidence: 50, is_monitored: false,
           ig_last_post_at: null, places_verified: false }
}

describe('busca', () => {
  it('normalize tira acento e caixa', () => {
    expect(normalize('Trackers, R. Augusta')).toBe('trackers, r. augusta')
    expect(normalize('TATUAPÉ')).toBe('tatuape')
  })
  it('filterVenues casa nome OU endereco', () => {
    const vs = [venue(1, 'Selva Club', 'R. Augusta 501'), venue(2, 'D-Edge', 'Al. Olga 170')]
    expect(filterVenues(vs, 'augusta')).toHaveLength(1)
    expect(filterVenues(vs, 'd-edge')).toHaveLength(1)
    expect(filterVenues(vs, '')).toHaveLength(2)
  })
})

describe('LocaisTab', () => {
  it('lista, busca e expande', async () => {
    render(<LocaisTab venues={[venue(1, 'Selva Club', 'R. Augusta 501'), venue(2, 'D-Edge')]}
                      events={[]} onOpenEvent={() => {}} />)
    expect(screen.getByText('Selva Club')).toBeInTheDocument()
    expect(screen.getByText('D-Edge')).toBeInTheDocument()
    await userEvent.type(screen.getByRole('textbox'), 'selva')
    expect(screen.queryByText('D-Edge')).toBeNull()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/components/VenueCard.test.tsx src/tabs/LocaisTab.test.tsx`
Expected: FAIL (módulos não existem)

- [ ] **Step 3: Implement**

```tsx
// web/src/components/VenueCard.tsx
import type { VenueOut } from '../api/types'
import type { EventWithGeo } from '../data/join'
import { igActivity } from '../data/vivacity'
import { fmtDate } from './EventCard'

export function VenueCard({ venue, upcoming, expanded, onToggle, onOpenEvent, now }: {
  venue: VenueOut; upcoming: EventWithGeo[]; expanded: boolean
  onToggle: () => void; onOpenEvent: (e: EventWithGeo) => void; now?: Date
}) {
  const ig = igActivity(venue.ig_last_post_at, now)
  const n = upcoming.length
  const mapsHref = `https://maps.google.com/?q=${encodeURIComponent(
    `${venue.name} ${venue.address ?? 'São Paulo'}`)}`
  return (
    <div className="b-card" style={{ margin: '8px 12px 0', padding: 10 }} onClick={onToggle}>
      <div className="title" style={{ fontSize: 15 }}>{venue.name}</div>
      <div style={{ marginTop: 5, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {venue.places_verified && <span className="tag ghost">✓ VERIFICADO</span>}
        {ig === 'hoje' && <span className="tag" style={{ background: 'var(--green)' }}>IG HOJE</span>}
        {ig === 'ativo' && <span className="tag ghost" style={{ color: 'var(--green)' }}>IG ATIVO</span>}
        {n > 0 && <span className="tag">{n} {n === 1 ? 'FESTA' : 'FESTAS'}</span>}
        {venue.category && <span className="tag ghost">{venue.category}</span>}
      </div>
      {expanded && (
        <div style={{ marginTop: 8 }} onClick={(e) => e.stopPropagation()}>
          {venue.address && <div className="meta">{venue.address}</div>}
          {upcoming.slice(0, 5).map((e) => (
            <div key={e.id} style={{ fontSize: 11, fontWeight: 700, marginTop: 4, cursor: 'pointer' }}
                 onClick={() => onOpenEvent(e)}>
              <span style={{ color: 'var(--pink)' }}>{fmtDate(e.starts_at)}</span> {e.name}
            </div>
          ))}
          <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
            {venue.instagram && (
              <a className="chip grn" href={`https://instagram.com/${venue.instagram}`}
                 target="_blank" rel="noreferrer">IG</a>
            )}
            {venue.website && (
              <a className="chip" href={venue.website} target="_blank" rel="noreferrer">SITE</a>
            )}
            <a className="chip" href={mapsHref} target="_blank" rel="noreferrer">MAPA</a>
          </div>
        </div>
      )}
    </div>
  )
}
```

```tsx
// web/src/tabs/LocaisTab.tsx
import { useMemo, useState } from 'react'
import type { VenueOut } from '../api/types'
import type { EventWithGeo } from '../data/join'
import { upcomingEventsAtVenue } from '../data/venueEvents'
import { igActivity } from '../data/vivacity'
import { VenueCard } from '../components/VenueCard'

export function normalize(s: string): string {
  return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
}

export function filterVenues(venues: VenueOut[], q: string): VenueOut[] {
  const nq = normalize(q.trim())
  if (!nq) return venues
  return venues.filter((v) =>
    normalize(v.name).includes(nq) || (v.address != null && normalize(v.address).includes(nq)))
}

export function LocaisTab({ venues, events, onOpenEvent }: {
  venues: VenueOut[]; events: EventWithGeo[]; onOpenEvent: (e: EventWithGeo) => void
}) {
  const [q, setQ] = useState('')
  const [openId, setOpenId] = useState<number | null>(null)
  const upcomingBy = useMemo(() => {
    const m = new Map<number, EventWithGeo[]>()
    for (const v of venues) m.set(v.id, upcomingEventsAtVenue(events, v.id))
    return m
  }, [venues, events])

  const shown = useMemo(() => {
    const fs = filterVenues(venues, q)
    // vivos primeiro: com festa marcada > IG mais recente > confianca
    return [...fs].sort((a, b) => {
      const fa = (upcomingBy.get(a.id)?.length ?? 0) > 0 ? 1 : 0
      const fb = (upcomingBy.get(b.id)?.length ?? 0) > 0 ? 1 : 0
      if (fa !== fb) return fb - fa
      const ia = igActivity(a.ig_last_post_at) ? 1 : 0
      const ib = igActivity(b.ig_last_post_at) ? 1 : 0
      if (ia !== ib) return ib - ia
      return b.effective_confidence - a.effective_confidence
    })
  }, [venues, q, upcomingBy])

  return (
    <div style={{ height: '100%', overflowY: 'auto', paddingBottom: 70 }}>
      <div style={{ padding: '14px 12px 4px' }}>
        <div className="hline" style={{ fontSize: 30 }}>LOCAIS<br />
          <span style={{ color: 'var(--green)' }}>VIVOS</span></div>
        <div className="label" style={{ marginTop: 5 }}>{shown.length} LOCAIS</div>
      </div>
      <div style={{ padding: '6px 12px' }}>
        <input value={q} onChange={(e) => setQ(e.target.value)}
               placeholder="BUSCAR LOCAL OU RUA"
               style={{ width: '100%', padding: '9px 10px', background: 'var(--panel)',
                        border: '1px solid var(--line)', color: 'var(--text)',
                        fontWeight: 700, fontSize: 13, letterSpacing: '0.04em' }} />
      </div>
      {shown.map((v) => (
        <VenueCard key={v.id} venue={v} upcoming={upcomingBy.get(v.id) ?? []}
                   expanded={openId === v.id}
                   onToggle={() => setOpenId(openId === v.id ? null : v.id)}
                   onOpenEvent={onOpenEvent} />
      ))}
      {shown.length === 0 && <div className="empty">Nenhum local com essa busca.</div>}
    </div>
  )
}
```

- [ ] **Step 4: Wire no `App.tsx`** — substitua o placeholder:

```tsx
  const locais = <LocaisTab venues={venues} events={events} onOpenEvent={openEvent} />
```

(`events` SEM filtro client — o diretório independe dos filtros de festa. Import de `LocaisTab`.)

- [ ] **Step 5: Run tests + typecheck**

Run: `cd web && npx vitest run && npx tsc -b`
Expected: PASS (suíte inteira)

- [ ] **Step 6: Commit**

```bash
git add web/src/components/VenueCard.tsx web/src/components/VenueCard.test.tsx web/src/tabs/LocaisTab.tsx web/src/tabs/LocaisTab.test.tsx web/src/App.tsx
git commit -m "feat(web): LocaisTab + VenueCard — busca, badges de vivacidade, festas futuras, IG/SITE/MAPA"
```

---

### Task 14: PWA — manifest + ícones + link

**Files:**
- Create: `web/public/manifest.webmanifest`, `web/public/icon-192.png`, `web/public/icon-512.png`
- Modify: `web/index.html`

- [ ] **Step 1: Manifest**

```json
{
  "name": "RADAR★SP",
  "short_name": "RADAR★SP",
  "description": "Festas e baladas de São Paulo — esta noite",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#000000",
  "theme_color": "#000000",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

- [ ] **Step 2: Ícones** (losango rosa com contorno verde sobre preto — o pin do mapa; Pillow já está no venv). Rodar da raiz do repo:

```bash
.venv/Scripts/python - <<'EOF'
from PIL import Image, ImageDraw
for size in (192, 512):
    img = Image.new("RGB", (size, size), "#000000")
    d = ImageDraw.Draw(img)
    c, r = size / 2, size * 0.32
    d.polygon([(c, c - r), (c + r, c), (c, c + r), (c - r, c)],
              fill="#ff2e88", outline="#00ff85", width=max(3, size // 40))
    img.save(f"web/public/icon-{size}.png")
    print(f"icon-{size}.png ok")
EOF
```

- [ ] **Step 3: Link no `index.html`** — dentro do `<head>` (o `theme-color` preto já existe):

```html
    <link rel="manifest" href="/manifest.webmanifest" />
    <link rel="apple-touch-icon" href="/icon-192.png" />
```

- [ ] **Step 4: Verify**

Run: `cd web && npm run build && ls dist/manifest.webmanifest dist/icon-192.png dist/icon-512.png`
Expected: build ok, os 3 arquivos no dist. (Instalabilidade real = smoke no Chrome: menu → "Instalar RADAR★SP".)

- [ ] **Step 5: Commit**

```bash
git add web/public/manifest.webmanifest web/public/icon-192.png web/public/icon-512.png web/index.html
git commit -m "feat(web): PWA manifest minimo + icones (losango brutalista) + apple-touch-icon"
```

---

### Task 15: Final — suítes completas + build + smoke visual

- [ ] **Step 1: Suítes completas**

```bash
.venv/Scripts/python -m pytest -q --basetemp=.pytest-tmp   # backend inteiro
cd web && npx vitest run && npx tsc -b && npm run build     # web inteiro
```

Expected: tudo verde (backend ≥130, web ≥45).

- [ ] **Step 2: Smoke visual (usuário)** — subir `docker compose up -d --wait` + uvicorn :8001 + `npm run dev`, e validar no navegador:
  - FESTAS: chip ≡ FILTROS abre o sheet; marcar SOM/bairro/extras muda "VER N FESTAS →" ao vivo; LIMPAR zera; contador aparece no chip.
  - MAPA: chips no topo; CAMADAS liga/desliga losangos, bolinhas verdes e "só com festa hoje"; gaveta arrasta entre 3 alturas, tap alterna; card na gaveta abre o detalhe.
  - LOCAIS: busca por nome/rua; badges ✓ VERIFICADO / IG HOJE / N FESTAS; expandir mostra festas + IG/SITE/MAPA.
  - PERTO DE MIM: conceder GPS filtra; negar apaga o chip sem quebrar o resto.
  - PWA: Chrome → instalar; abre standalone com ícone.
  - `/flyers/<shortcode>.json` responde 404 (M1) e as imagens seguem 200.
- [ ] **Step 3:** Smoke aprovado → merge no master + deletar branch (finishing-a-development-branch).

---

## Riscos & notas pro executor

- **jsdom vs mapa GL:** MapaTab.test MOCKA `../map/MapView` (canvas não roda em jsdom) — não tente renderizar o MapView real em teste.
- **CSS do maplibre:** qualquer regra nova pra popup precisa do prefixo `.maplibregl-popup` (lição C-1 — o css do maplibre entra no bundle DEPOIS do theme.css).
- **Fixtures antigas:** `VenueOut` ganhou 2 campos → todo literal em teste precisa de `ig_last_post_at: null, places_verified: false`.
- **`FilterState` mudou de shape** (sem `genre`, com `genres/date/bairro/nearMe/extras`) → use spread de `initialFilters` nas fixtures.
- **Z-index:** tabbar 30 < FilterSheet 40 < EventDetail (garanta ≥50 ao mexer); Drawer 20 fica abaixo de tudo isso.
- **Não-objetivos (spec §5):** sem clusterização, sem service worker, sem favoritos, sem lib de gestos.
