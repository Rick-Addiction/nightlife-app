import { useEffect, useMemo, useReducer, useState } from 'react'
import './theme.css'
import { fetchEvents, fetchVenues } from './api/client'
import { joinEventsWithVenues, type EventWithGeo } from './data/join'
import { filterReducer, initialFilters, queryFromFilters } from './filters/state'
import { FilterBar, type View } from './filters/FilterBar'
import { EventList } from './list/EventList'
import { MapView } from './map/MapView'

export default function App() {
  const [filters, dispatch] = useReducer(filterReducer, initialFilters)
  const [view, setView] = useState<View>('split')
  const [events, setEvents] = useState<EventWithGeo[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    Promise.all([fetchEvents(queryFromFilters(filters)), fetchVenues()])
      .then(([evs, vns]) => { if (alive) setEvents(joinEventsWithVenues(evs, vns)) })
      .catch((e) => { if (alive) setError(String(e)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [filters, reloadKey])

  const genres = useMemo(
    () => Array.from(new Set(events.map((e) => e.genre).filter((g): g is string => !!g))).sort(),
    [events],
  )

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <FilterBar filters={filters} genres={genres} dispatch={dispatch} view={view} onView={setView} />
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
              <MapView events={events} selectedId={selectedId} onSelect={setSelectedId} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
