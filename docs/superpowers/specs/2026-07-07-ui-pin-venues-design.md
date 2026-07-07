# Nightlife App — UI: pinar venues no mapa — Design (Spec)

- **Data:** 2026-07-07
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** O mapa da UI é hoje **event-centric**: cada pin é um evento, posicionado no venue. Com o geocoding e a descoberta via Places, o banco tem ~800 nightclubs geocodados — mas eles só aparecem no mapa se tiverem evento. Esta feature adiciona os **venues** ao mapa como uma camada própria, fechando o arco que começou na Rua Augusta ("só achei uma"): o "mapa cheio de clubes".

---

## 1. Objetivo

Mostrar os venues relevantes (nightclubs geocodados) no mapa como uma camada de pontos discretos, com os eventos futuros destacados por cima. Clicar num venue abre um popup com nome, categoria, eventos futuros ali e links de IG/site. Um toggle liga/desliga a camada de locais.

## 2. Decisões travadas (do brainstorming)

1. **Camada dupla:** venues sempre visíveis (dim, base) + eventos destacados por cima (brilhantes, inalterados). Vê os clubes e as festas ao mesmo tempo.
2. **Clique no venue → popup** com nome, categoria, eventos futuros do local (reusa o array `events` já buscado), links IG/site se existirem.
3. **Todos os ~800 pontos sempre + toggle** "Locais" na FilterBar pra ligar/desligar a camada. Começa **ligado**.
4. **Técnica:** venues como **camada GL** (`Source` GeoJSON + `Layer` circle do MapLibre — aguenta milhares, culla off-screen), NÃO como `<Marker>` DOM (800 DOM travariam). Eventos seguem como Markers DOM (são poucos).

## 3. Arquitetura & arquivos

O `App` já busca `events` + `venues` (o fetch de venues alimenta o join que dá geo aos eventos). Agora também repassa `venues` + um estado `showVenues` pro `MapView`. O backend quase não muda: só `instagram`/`website` no `VenueOut`.

**Arquivos novos (frontend):**
- `web/src/map/geojson.ts` — `venuesToFeatureCollection(venues)` (puro).
- `web/src/data/venueEvents.ts` — `upcomingEventsAtVenue(events, venueId)` (puro).
- Testes: `web/src/map/geojson.test.ts`, `web/src/data/venueEvents.test.ts`.

**Arquivos modificados:**
- `web/src/map/MapView.tsx` — camada de venues + popup de venue.
- `web/src/filters/FilterBar.tsx` — checkbox "Locais".
- `web/src/App.tsx` — estado `showVenues`, repasse de props.
- `web/src/api/types.ts` — `instagram`/`website` em `VenueOut`.
- `src/nightlife/api/schemas.py` — `instagram`/`website` em `VenueOut`.
- `web/src/filters/FilterBar.test.tsx` — teste do toggle.

## 4. Componentes

### 4A. `geojson.ts` (puro)

```ts
import type { VenueOut } from '../api/types'
import type { FeatureCollection, Point } from 'geojson'

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

### 4B. `venueEvents.ts` (puro)

```ts
import type { EventWithGeo } from './join'

export function upcomingEventsAtVenue(events: EventWithGeo[], venueId: number): EventWithGeo[] {
  return events
    .filter((e) => e.venue_id === venueId)
    .sort((a, b) => (a.starts_at ?? '').localeCompare(b.starts_at ?? ''))
}
```
(`events` já vem filtrado por data pelo fetch principal — futuros por padrão; aqui só recorta por venue e ordena.)

### 4C. `MapView.tsx` (modifica)

- Props novos: `venues: VenueOut[]`, `showVenues: boolean`.
- Quando `showVenues`, renderiza:
  ```tsx
  <Source id="venues" type="geojson" data={venuesToFeatureCollection(venues)}>
    <Layer id="venues" type="circle" paint={{
      'circle-radius': 3.5,
      'circle-color': '#5a6b8a',
      'circle-opacity': 0.7,
      'circle-stroke-width': 0,
    }} />
  </Source>
  ```
- `<Map ... interactiveLayerIds={showVenues ? ['venues'] : []} onClick={onMapClick}>`: `onMapClick` lê `e.features?.[0]` da camada `venues`, guarda `{id, name, category, lng, lat}` do venue clicado → popup.
- Popup do venue: nome (`<strong>`), categoria, lista de `upcomingEventsAtVenue(events, id)` (nome + data curta), e links `instagram`/`website` se presentes. Fechável.
- Os `<Marker>` de evento continuam por cima (DOM), clicáveis independente da camada GL.

### 4D. `FilterBar.tsx` (modifica)

Adiciona um checkbox "Locais" (à direita do toggle de view), controlado por props `showVenues: boolean` + `onToggleVenues: () => void`.

### 4E. `App.tsx` (modifica)

`const [showVenues, setShowVenues] = useState(true)`. Passa `venues`+`showVenues` pro `MapView` e `showVenues`+`onToggleVenues` pra `FilterBar`. (Guarda o array de `venues` do fetch — hoje ele é consumido só no join e descartado; passa a viver em estado.)

### 4F. Backend — `VenueOut` (schemas.py + types.ts)

Adiciona `instagram: str | None = None` e `website: str | None = None` ao `VenueOut` (o model `Venue` já tem os campos; `from_attributes` popula). Espelha no `VenueOut` do TS.

## 5. Estilo

- Venue: circle dim `#5a6b8a`, raio 3.5, opacidade 0.7 — fundo discreto.
- Venue selecionado: raio/opacidade maiores (via feature-state ou um segundo layer filtrado pelo id selecionado).
- Eventos: mantêm ciano `#22e0e0` / rosa `#e055c0` brilhante, por cima.
- Efeito: "mapa cheio de clubes" de fundo, festas saltando.

## 6. Não-objetivos (YAGNI)

- Clusterização (decidido: todos os pontos + toggle).
- Filtrar a lista lateral ao clicar num venue (o clique abre popup, não mexe na lista).
- Filtros de venue (categoria/confiança) na UI — a camada mostra os relevantes que a API já retorna.
- Bbox no fetch de venues — 800 num payload é leve; a GL culla off-screen.
- Rich details do venue (fotos, rating) — só nome/categoria/eventos/links.

## 7. Testes

- **`venuesToFeatureCollection` (puro):** venues com geo → features com coords `[lng, lat]` e props `id/name/category`; venues sem geo são pulados; lista vazia → `features: []`.
- **`upcomingEventsAtVenue` (puro):** filtra por `venue_id`; ordena por `starts_at`; `[]` quando o venue não tem eventos.
- **`FilterBar` (Testing Library):** renderiza o checkbox "Locais"; clicar chama `onToggleVenues`.
- **`MapView`:** sem teste unitário (canvas/maplibre — mesmo padrão atual; a lógica testável está nos helpers puros).
- **Backend:** `GET /venues` inclui `instagram`/`website` no payload (um venue com esses campos preenchidos aparece no JSON).
- Suítes verdes: `web/` (Vitest) e backend (pytest).

## 8. Definition of Done

- [ ] `venuesToFeatureCollection` + `upcomingEventsAtVenue` puros e testados.
- [ ] `VenueOut` (schemas.py + types.ts) com `instagram`/`website`; teste de API.
- [ ] `MapView` com camada GL de venues + popup (nome/categoria/eventos/links); eventos por cima intactos.
- [ ] `FilterBar` com toggle "Locais" (começa ligado); testado.
- [ ] `App` liga tudo (estado `showVenues`, repasse de `venues`).
- [ ] Suítes verdes (Vitest + pytest). Smoke visual: subir a UI, ver os ~800 venues dim + eventos brilhantes, clicar num venue e ver o popup.
