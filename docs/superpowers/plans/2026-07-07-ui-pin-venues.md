# UI Pin Venues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar os ~800 venues geocodados como uma camada GL no mapa da UI (dim, de fundo), com os eventos brilhantes por cima; clicar num venue abre um popup com nome/categoria/eventos futuros/links; um toggle "Locais" liga/desliga a camada.

**Architecture:** Frontend React + react-map-gl/maplibre. Venues renderizados como `Source` GeoJSON + `Layer` circle (aguenta milhares; culla off-screen), NÃO como `<Marker>` DOM. Lógica testável em helpers puros (`geojson.ts`, `venueEvents.ts`); `MapView` só faz a fiação (canvas, sem teste unitário — padrão atual). Backend só ganha `instagram`/`website` no `VenueOut`.

**Tech Stack:** React 19, Vite, TypeScript, react-map-gl/maplibre, MapLibre GL, Vitest + Testing Library (web); FastAPI/Pydantic + pytest (backend).

**Referências do código existente:**
- `web/src/api/types.ts`: `VenueOut { id, name, category, lat, lng, address, status, confidence, effective_confidence, is_monitored }`; `EventOut`.
- `web/src/data/join.ts`: `EventWithGeo extends EventOut { venueName, lat, lng, mappable }`; `joinEventsWithVenues`.
- `web/src/App.tsx`: busca `events`+`venues`, hoje descarta `venues` após o join; renderiza `FilterBar` + `EventList` + `MapView`.
- `web/src/map/MapView.tsx`: `Map` (react-map-gl/maplibre) com `<Marker>` por evento + `<Popup>` de evento. Cores: evento normal `#22e0e0`, selecionado `#e055c0`.
- `web/src/filters/FilterBar.tsx`: barra com presets/gênero/confiança + botões de view. Props `{ filters, genres, dispatch, view, onView }`.
- `src/nightlife/api/schemas.py`: `VenueOut` Pydantic (`from_attributes=True`). O model `Venue` já tem `instagram`/`website`.
- `tests/test_api.py`: usa `TestClient(app)` com `app.dependency_overrides[get_session]`; fixture `session`.

**Comandos de teste:**
- Web: a partir de `web/`, `npx vitest run <caminho relativo>` (ex.: `npx vitest run src/map/geojson.test.ts`).
- Backend: `.venv/Scripts/python -m pytest tests/test_api.py -v` (Postgres na 5434 de pé; se `tmp_path` estourar, use `--basetemp=<scratchpad>/bt`).

**Convenção de commit:** cada commit termina com o trailer `Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu`.

---

### Task 1: Backend — `instagram`/`website` no `VenueOut`

**Files:**
- Modify: `src/nightlife/api/schemas.py` (classe `VenueOut`)
- Modify: `web/src/api/types.ts` (interface `VenueOut`)
- Test: `tests/test_api.py` (novo teste)

- [ ] **Step 1: Write the failing test**

Adicionar em `tests/test_api.py`:

```python
def test_venue_out_inclui_instagram_e_website(session):
    v = Venue(name="D-Edge", category="nightclub", lat=-23.53, lng=-46.66,
              status="operational", confidence=80, is_monitored=True,
              instagram="dedgeclub", website="https://d-edge.com.br")
    session.add(v)
    session.flush()
    client = _client(session)
    try:
        row = next(x for x in client.get("/venues").json() if x["name"] == "D-Edge")
        assert row["instagram"] == "dedgeclub"
        assert row["website"] == "https://d-edge.com.br"
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_api.py::test_venue_out_inclui_instagram_e_website -v`
Expected: FAIL com `KeyError: 'instagram'` (o campo não está no payload).

- [ ] **Step 3: Write minimal implementation**

Em `src/nightlife/api/schemas.py`, adicionar dois campos à classe `VenueOut` (depois de `address`):

```python
class VenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    category: str | None = None
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    instagram: str | None = None
    website: str | None = None
    status: str
    confidence: int
    effective_confidence: int = 0
    is_monitored: bool
```

Em `web/src/api/types.ts`, adicionar à interface `VenueOut` (depois de `address`):

```ts
export interface VenueOut {
  id: number
  name: string
  category: string | null
  lat: number | null
  lng: number | null
  address: string | null
  instagram: string | null
  website: string | null
  status: string
  confidence: number
  effective_confidence: number
  is_monitored: boolean
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_api.py::test_venue_out_inclui_instagram_e_website -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/api/schemas.py web/src/api/types.ts tests/test_api.py
git commit -m "feat: instagram/website no VenueOut (API + TS)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 2: `geojson.ts` — venues → FeatureCollection (puro)

**Files:**
- Create: `web/src/map/geojson.ts`
- Test: `web/src/map/geojson.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// web/src/map/geojson.test.ts
import { describe, it, expect } from 'vitest'
import { venuesToFeatureCollection } from './geojson'
import type { VenueOut } from '../api/types'

const venue = (over: Partial<VenueOut>): VenueOut => ({
  id: 1, name: 'X', category: 'nightclub', lat: -23.5, lng: -46.6, address: null,
  instagram: null, website: null, status: 'operational', confidence: 50,
  effective_confidence: 50, is_monitored: false, ...over,
})

describe('venuesToFeatureCollection', () => {
  it('mapeia venue com geo para Feature com coords [lng, lat] e props', () => {
    const fc = venuesToFeatureCollection([venue({ id: 7, name: 'D-Edge', lat: -23.53, lng: -46.66 })])
    expect(fc.features).toHaveLength(1)
    const f = fc.features[0]
    expect(f.geometry.coordinates).toEqual([-46.66, -23.53])
    expect(f.properties).toMatchObject({ id: 7, name: 'D-Edge', category: 'nightclub' })
  })

  it('pula venues sem geo', () => {
    const fc = venuesToFeatureCollection([venue({ lat: null }), venue({ lng: null }), venue({ id: 9 })])
    expect(fc.features).toHaveLength(1)
    expect(fc.features[0].properties!.id).toBe(9)
  })

  it('lista vazia vira FeatureCollection vazia', () => {
    expect(venuesToFeatureCollection([]).features).toEqual([])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (de `web/`): `npx vitest run src/map/geojson.test.ts`
Expected: FAIL com erro de import (`venuesToFeatureCollection` não existe).

- [ ] **Step 3: Write minimal implementation**

```ts
// web/src/map/geojson.ts
import type { FeatureCollection, Point } from 'geojson'
import type { VenueOut } from '../api/types'

export function venuesToFeatureCollection(venues: VenueOut[]): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: venues
      .filter((v) => v.lat != null && v.lng != null)
      .map((v) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [v.lng!, v.lat!] },
        properties: { id: v.id, name: v.name, category: v.category },
      })),
  }
}
```

Nota: `geojson` types vêm transitivamente com `maplibre-gl`. Se o TS reclamar do módulo `'geojson'`, trocar os imports por tipos inline: `type Point = { type: 'Point'; coordinates: [number, number] }` e retornar `{ type: 'FeatureCollection'; features: Array<{ type: 'Feature'; geometry: Point; properties: Record<string, unknown> }> }`.

- [ ] **Step 4: Run test to verify it passes**

Run (de `web/`): `npx vitest run src/map/geojson.test.ts`
Expected: PASS (3 testes)

- [ ] **Step 5: Commit**

```bash
git add web/src/map/geojson.ts web/src/map/geojson.test.ts
git commit -m "feat: venuesToFeatureCollection (venues -> GeoJSON, puro)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 3: `venueEvents.ts` — eventos futuros de um venue (puro)

**Files:**
- Create: `web/src/data/venueEvents.ts`
- Test: `web/src/data/venueEvents.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// web/src/data/venueEvents.test.ts
import { describe, it, expect } from 'vitest'
import { upcomingEventsAtVenue } from './venueEvents'
import type { EventWithGeo } from './join'

const ev = (over: Partial<EventWithGeo>): EventWithGeo => ({
  id: 1, name: 'Festa', starts_at: '2026-07-10T23:00:00-03:00', ends_at: null,
  venue_id: 5, status: 'scheduled', genre: null, ticket_url: null, confidence: 40,
  effective_confidence: 40, venueName: 'D-Edge', lat: -23.5, lng: -46.6, mappable: true, ...over,
})

describe('upcomingEventsAtVenue', () => {
  it('filtra pelo venue_id e ordena por data', () => {
    const events = [
      ev({ id: 1, venue_id: 5, starts_at: '2026-07-20T23:00:00-03:00' }),
      ev({ id: 2, venue_id: 9, starts_at: '2026-07-11T23:00:00-03:00' }),
      ev({ id: 3, venue_id: 5, starts_at: '2026-07-10T23:00:00-03:00' }),
    ]
    const out = upcomingEventsAtVenue(events, 5)
    expect(out.map((e) => e.id)).toEqual([3, 1])  // so venue 5, mais cedo primeiro
  })

  it('venue sem eventos vira lista vazia', () => {
    expect(upcomingEventsAtVenue([ev({ venue_id: 1 })], 999)).toEqual([])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (de `web/`): `npx vitest run src/data/venueEvents.test.ts`
Expected: FAIL com erro de import.

- [ ] **Step 3: Write minimal implementation**

```ts
// web/src/data/venueEvents.ts
import type { EventWithGeo } from './join'

export function upcomingEventsAtVenue(events: EventWithGeo[], venueId: number): EventWithGeo[] {
  return events
    .filter((e) => e.venue_id === venueId)
    .sort((a, b) => (a.starts_at ?? '').localeCompare(b.starts_at ?? ''))
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (de `web/`): `npx vitest run src/data/venueEvents.test.ts`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add web/src/data/venueEvents.ts web/src/data/venueEvents.test.ts
git commit -m "feat: upcomingEventsAtVenue (eventos futuros de um venue, puro)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 4: `FilterBar` — toggle "Locais"

**Files:**
- Modify: `web/src/filters/FilterBar.tsx`
- Test: `web/src/filters/FilterBar.test.tsx` (novo teste)

- [ ] **Step 1: Write the failing test**

Adicionar em `web/src/filters/FilterBar.test.tsx` (dentro do `describe('FilterBar', ...)`):

```tsx
  it('dispara onToggleVenues ao clicar no checkbox Locais', async () => {
    const onToggleVenues = vi.fn()
    render(<FilterBar filters={initialFilters} genres={[]} dispatch={() => {}}
                     view="split" onView={() => {}} showVenues={true} onToggleVenues={onToggleVenues} />)
    await userEvent.click(screen.getByLabelText(/locais/i))
    expect(onToggleVenues).toHaveBeenCalled()
  })
```

Também atualizar as DUAS chamadas `render(<FilterBar ... />)` já existentes no arquivo para incluir os props novos `showVenues={true} onToggleVenues={() => {}}` (senão o TS/prop-types reclama).

- [ ] **Step 2: Run test to verify it fails**

Run (de `web/`): `npx vitest run src/filters/FilterBar.test.tsx`
Expected: FAIL (o checkbox "Locais" não existe ainda).

- [ ] **Step 3: Write minimal implementation**

Em `web/src/filters/FilterBar.tsx`, estender a assinatura de props e adicionar o checkbox. A assinatura vira:

```tsx
export function FilterBar({ filters, genres, dispatch, view, onView, showVenues, onToggleVenues }: {
  filters: FilterState
  genres: string[]
  dispatch: Dispatch<FilterAction>
  view: View
  onView: (v: View) => void
  showVenues: boolean
  onToggleVenues: () => void
}) {
```

E, dentro do `<div style={{ marginLeft: 'auto', ... }}>` (o bloco dos botões de view), adicionar o checkbox ANTES dos botões:

```tsx
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, alignItems: 'center' }}>
        <label style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <input type="checkbox" checked={showVenues} onChange={onToggleVenues} />
          Locais
        </label>
        <div style={{ display: 'flex', gap: 4 }}>
          <button onClick={() => onView('list')} aria-pressed={view === 'list'}
                  style={{ fontWeight: view === 'list' ? 700 : 400 }}>Só lista</button>
          <button onClick={() => onView('split')} aria-pressed={view === 'split'}
                  style={{ fontWeight: view === 'split' ? 700 : 400 }}>Lista + Mapa</button>
        </div>
      </div>
```

(Substitui o `<div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>` atual que só tinha os dois botões.)

- [ ] **Step 4: Run test to verify it passes**

Run (de `web/`): `npx vitest run src/filters/FilterBar.test.tsx`
Expected: PASS (3 testes — os 2 antigos + o novo)

- [ ] **Step 5: Commit**

```bash
git add web/src/filters/FilterBar.tsx web/src/filters/FilterBar.test.tsx
git commit -m "feat: toggle Locais na FilterBar

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 5: `MapView` camada de venues + popup, e fiação no `App`

**Files:**
- Modify: `web/src/map/MapView.tsx`
- Modify: `web/src/App.tsx`

Contexto: `MapView` é canvas/maplibre — sem teste unitário (padrão atual, não há `MapView.test`). A lógica testável já está nos helpers (Tasks 2/3). Esta task é fiação; a verificação é o smoke visual da Task 6.

- [ ] **Step 1: Reescrever `web/src/map/MapView.tsx`**

```tsx
import { Map, Marker, Popup, Source, Layer } from 'react-map-gl/maplibre'
import type { MapLayerMouseEvent } from 'react-map-gl/maplibre'
import { useState } from 'react'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { EventWithGeo } from '../data/join'
import type { VenueOut } from '../api/types'
import { venuesToFeatureCollection } from './geojson'
import { upcomingEventsAtVenue } from '../data/venueEvents'

const MAP_STYLE = {
  version: 8 as const,
  sources: {
    carto: {
      type: 'raster' as const,
      tiles: ['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap © CARTO',
    },
  },
  layers: [{ id: 'carto', type: 'raster' as const, source: 'carto' }],
}

type SelVenue = { id: number; name: string; category: string | null; lng: number; lat: number }

function fmtDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
}

export function MapView({ events, venues, selectedId, onSelect, showVenues }: {
  events: EventWithGeo[]; venues: VenueOut[]; selectedId: number | null
  onSelect: (id: number) => void; showVenues: boolean
}) {
  const [popupId, setPopupId] = useState<number | null>(null)
  const [selVenue, setSelVenue] = useState<SelVenue | null>(null)
  const mappable = events.filter((e) => e.mappable)
  const popup = mappable.find((e) => e.id === (popupId ?? selectedId))

  const onMapClick = (e: MapLayerMouseEvent) => {
    const f = e.features?.[0]
    if (f && f.layer.id === 'venues' && f.geometry.type === 'Point') {
      const [lng, lat] = f.geometry.coordinates as [number, number]
      const p = f.properties as { id: number; name: string; category: string | null }
      setSelVenue({ id: p.id, name: p.name, category: p.category, lng, lat })
    } else {
      setSelVenue(null)
    }
  }

  const venueEvents = selVenue ? upcomingEventsAtVenue(events, selVenue.id) : []

  return (
    <Map
      initialViewState={{ longitude: -46.63, latitude: -23.55, zoom: 11 }}
      mapStyle={MAP_STYLE}
      style={{ width: '100%', height: '100%' }}
      interactiveLayerIds={showVenues ? ['venues'] : []}
      onClick={onMapClick}
    >
      {showVenues && (
        <Source id="venues" type="geojson" data={venuesToFeatureCollection(venues)}>
          <Layer id="venues" type="circle" paint={{
            'circle-radius': 3.5,
            'circle-color': '#5a6b8a',
            'circle-opacity': 0.7,
          }} />
          <Layer id="venues-sel" type="circle"
                 filter={['==', ['get', 'id'], selVenue?.id ?? -1]}
                 paint={{ 'circle-radius': 7, 'circle-color': '#8fb0ff', 'circle-opacity': 0.95 }} />
        </Source>
      )}

      {mappable.map((e) => (
        <Marker key={e.id} longitude={e.lng!} latitude={e.lat!} anchor="bottom"
                onClick={(ev) => { ev.originalEvent.stopPropagation(); onSelect(e.id); setPopupId(e.id) }}>
          <div style={{
            width: 12, height: 12, borderRadius: '50%',
            background: e.id === selectedId ? '#e055c0' : '#22e0e0',
            boxShadow: `0 0 8px ${e.id === selectedId ? '#e055c0' : '#22e0e0'}`,
            cursor: 'pointer',
          }} />
        </Marker>
      ))}

      {popup && (
        <Popup longitude={popup.lng!} latitude={popup.lat!} anchor="top"
               onClose={() => setPopupId(null)} closeButton={false}>
          <strong>{popup.name}</strong><br />{popup.venueName}
        </Popup>
      )}

      {selVenue && (
        <Popup longitude={selVenue.lng} latitude={selVenue.lat} anchor="top"
               onClose={() => setSelVenue(null)} closeButton={true} maxWidth="240px">
          <strong>{selVenue.name}</strong>
          {selVenue.category && <div style={{ opacity: 0.7 }}>{selVenue.category}</div>}
          {venueEvents.length > 0 ? (
            <ul style={{ margin: '6px 0 0', paddingLeft: 16 }}>
              {venueEvents.slice(0, 5).map((e) => (
                <li key={e.id}>{fmtDate(e.starts_at)} — {e.name}</li>
              ))}
            </ul>
          ) : (
            <div style={{ opacity: 0.6, marginTop: 6 }}>sem eventos futuros</div>
          )}
          {(() => {
            const v = venues.find((x) => x.id === selVenue.id)
            return (
              <div style={{ marginTop: 6, display: 'flex', gap: 8 }}>
                {v?.instagram && <a href={`https://instagram.com/${v.instagram}`} target="_blank" rel="noreferrer">IG</a>}
                {v?.website && <a href={v.website} target="_blank" rel="noreferrer">site</a>}
              </div>
            )
          })()}
        </Popup>
      )}
    </Map>
  )
}
```

- [ ] **Step 2: Atualizar `web/src/App.tsx`** para guardar `venues` em estado e passar as props.

Trocar o import e o corpo relevante. Adicionar `VenueOut` ao import de types e:

No topo do componente, junto aos outros `useState`:
```tsx
  const [venues, setVenues] = useState<VenueOut[]>([])
  const [showVenues, setShowVenues] = useState(true)
```
Import: `import type { VenueOut } from './api/types'`.

No `useEffect` do fetch principal, guardar os venues também:
```tsx
    Promise.all([fetchEvents(queryFromFilters(filters)), fetchVenues()])
      .then(([evs, vns]) => { if (alive) { setEvents(joinEventsWithVenues(evs, vns)); setVenues(vns) } })
```

Passar props para `FilterBar` e `MapView`:
```tsx
      <FilterBar filters={filters} genres={genres} dispatch={dispatch} view={view} onView={setView}
                 showVenues={showVenues} onToggleVenues={() => setShowVenues((s) => !s)} />
```
```tsx
            <div style={{ flex: 1 }}>
              <MapView events={events} venues={venues} selectedId={selectedId} onSelect={setSelectedId}
                       showVenues={showVenues} />
            </div>
```

- [ ] **Step 3: Type-check + build**

Run (de `web/`): `npx tsc --noEmit`
Expected: sem erros de tipo. (Se `MapLayerMouseEvent` ou `Source/Layer` não exportarem de `react-map-gl/maplibre` na versão instalada, verificar o export correto no pacote e ajustar o import — NÃO inventar; conferir em `web/node_modules/react-map-gl`.)

- [ ] **Step 4: Rodar a suíte web (nada deve quebrar)**

Run (de `web/`): `npx vitest run`
Expected: todos verdes (helpers + FilterBar; MapView não tem teste).

- [ ] **Step 5: Commit**

```bash
git add web/src/map/MapView.tsx web/src/App.tsx
git commit -m "feat: MapView camada GL de venues + popup; App liga o toggle

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 6: suítes completas + smoke visual

**Files:** nenhum novo (verificação).

- [ ] **Step 1: Suíte web**

Run (de `web/`): `npx vitest run`
Expected: todos verdes.

- [ ] **Step 2: Suíte backend**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -v` (e, se quiser, a suíte inteira com `--basetemp=<scratchpad>/bt`)
Expected: verdes, incluindo o novo `test_venue_out_inclui_instagram_e_website`.

- [ ] **Step 3: Type-check web**

Run (de `web/`): `npx tsc --noEmit`
Expected: sem erros.

- [ ] **Step 4: Smoke visual (manual — controlador sobe os servidores)**

Subir uvicorn (`:8001`) e o Vite dev, abrir a UI. Confirmar: os ~800 venues aparecem como pontinhos dim de fundo; os eventos brilhantes por cima; o toggle "Locais" liga/desliga a camada; clicar num venue abre o popup com nome/categoria/eventos futuros/links; a Augusta aparece cheia de pontos.

- [ ] **Step 5: Commit (se algum ajuste do smoke foi necessário)**

Se nada mudou, sem commit. Caso ajustes:

```bash
git add -A
git commit -m "chore: ajustes do smoke visual do pin de venues

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

## Notas de implementação

- **800 pontos numa camada GL** é trivial pro MapLibre (culla off-screen). NÃO usar `<Marker>` DOM pros venues.
- **Lógica testável nos helpers puros** (`geojson.ts`, `venueEvents.ts`); `MapView` é fiação de canvas, verificada por smoke — mesmo padrão do `MapView` atual (sem teste).
- **Eventos por cima:** os `<Marker>` DOM ficam acima da camada GL e capturam clique primeiro; o clique no venue vem via `interactiveLayerIds`/`onClick` do mapa. Sem conflito.
- **`geojson` types:** vêm com `maplibre-gl`. Se faltarem, usar tipos inline (ver nota na Task 2).
