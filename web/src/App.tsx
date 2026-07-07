import { useEffect, useReducer, useState } from 'react'
import './theme.css'
import { fetchEvents, fetchVenues } from './api/client'
import { joinEventsWithVenues, type EventWithGeo } from './data/join'
import { filterReducer, initialFilters, queryFromFilters } from './filters/state'
import { FilterBar, type View } from './filters/FilterBar'
import { EventList } from './list/EventList'
import { MapView } from './map/MapView'
import type { VenueOut } from './api/types'

export default function App() {
  const [filters, dispatch] = useReducer(filterReducer, initialFilters)
  const [view, setView] = useState<View>('split')
  const [events, setEvents] = useState<EventWithGeo[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [genres, setGenres] = useState<string[]>([])
  const [venues, setVenues] = useState<VenueOut[]>([])
  const [showVenues, setShowVenues] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    Promise.all([fetchEvents(queryFromFilters(filters)), fetchVenues()])
      .then(([evs, vns]) => { if (alive) { setEvents(joinEventsWithVenues(evs, vns)); setVenues(vns) } })
      .catch((e) => { if (alive) setError(String(e)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [filters, reloadKey])

  // Universo de generos: de um fetch NAO-filtrado (uma vez), pra o dropdown
  // nao colapsar quando um genero e selecionado (o fetch principal e filtrado).
  useEffect(() => {
    let alive = true
    fetchEvents({ include_past: true })
      .then((evs) => {
        if (!alive) return
        setGenres(Array.from(new Set(evs.map((e) => e.genre).filter((g): g is string => !!g))).sort())
      })
      .catch(() => { /* silencioso: dropdown so fica sem opcoes extras */ })
    return () => { alive = false }
  }, [])

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <FilterBar filters={filters} genres={genres} dispatch={dispatch} view={view} onView={setView}
                 showVenues={showVenues} onToggleVenues={() => setShowVenues((s) => !s)} />
      {error && (
        <div className="empty" style={{ color: '#e07dd0' }}>
          Não consegui falar com a API — o uvicorn está no ar? ({error})
          <div style={{ marginTop: 12 }}>
            <button onClick={() => setReloadKey((k) => k + 1)}>Tentar de novo</button>
          </div>
        </div>
      )}
      {loading && <div className="empty">Carregando…</div>}
      {!loading && !error && (
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <div style={{ width: view === 'split' ? '42%' : '100%', overflowY: 'auto' }}>
            <EventList events={events} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
          {view === 'split' && (
            <div style={{ flex: 1 }}>
              <MapView events={events} venues={venues} selectedId={selectedId} onSelect={setSelectedId}
                       showVenues={showVenues} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
