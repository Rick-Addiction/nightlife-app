import { useEffect, useMemo, useReducer, useState } from 'react'
import './theme.css'
import { fetchEvents, fetchVenues } from './api/client'
import type { VenueOut } from './api/types'
import { joinEventsWithVenues, type EventWithGeo } from './data/join'
import { activeFilterCount, filterReducer, initialFilters, queryFromFilters } from './filters/state'
import { applyClientFilters } from './filters/apply'
import { FestasTab } from './tabs/FestasTab'
import { MapaTab } from './tabs/MapaTab'
import { LocaisTab } from './tabs/LocaisTab'
import { BottomTabs, type Tab } from './components/BottomTabs'
import { EventDetail } from './components/EventDetail'
import { FilterSheet } from './components/FilterSheet'

function useIsDesktop(): boolean {
  const [is, setIs] = useState(() => window.matchMedia('(min-width: 768px)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)')
    const on = (e: MediaQueryListEvent) => setIs(e.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return is
}

export default function App() {
  const [filters, dispatch] = useReducer(filterReducer, initialFilters)
  const [tab, setTab] = useState<Tab>('festas')
  const [events, setEvents] = useState<EventWithGeo[]>([])
  const [venues, setVenues] = useState<VenueOut[]>([])
  const [open, setOpen] = useState<EventWithGeo | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [sheetOpen, setSheetOpen] = useState(false)
  const isDesktop = useIsDesktop()

  // filtros client-side sobre o array joinado; a API so recebe datas/confianca
  const filtered = useMemo(() => applyClientFilters(events, filters), [events, filters])
  const genreOptions = useMemo(
    () => [...new Set(events.map((e) => e.genre).filter((g): g is string => !!g))].sort(),
    [events])
  const activeCount = activeFilterCount(filters)
  // refetch SO quando a query da API muda — filtros client-side (genero,
  // bairro, gps, extras) nao devem derrubar a lista nem repintar o mapa
  const queryKey = JSON.stringify(queryFromFilters(filters))

  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    Promise.all([fetchEvents(JSON.parse(queryKey)), fetchVenues()])
      .then(([evs, vns]) => { if (alive) { setEvents(joinEventsWithVenues(evs, vns)); setVenues(vns) } })
      .catch((e) => { if (alive) setError(String(e)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [queryKey, reloadKey])

  const openEvent = (e: EventWithGeo) => { setOpen(e); setSelectedId(e.id) }

  const mapa = (
    <MapaTab events={filtered} venues={venues} filters={filters} dispatch={dispatch}
             selectedId={selectedId}
             onSelect={(id) => { const e = events.find((x) => x.id === id); if (e) openEvent(e) }}
             onOpenSheet={() => setSheetOpen(true)} activeCount={activeCount}
             withDrawer={!isDesktop} />
  )
  const festas = <FestasTab events={filtered} filters={filters} dispatch={dispatch} onOpen={openEvent}
                            activeCount={activeCount} onOpenSheet={() => setSheetOpen(true)} />
  const locais = <LocaisTab venues={venues} events={events} onOpenEvent={openEvent} />

  if (error) {
    return (
      <div className="empty" style={{ paddingTop: 80 }}>
        Não consegui falar com a API — o uvicorn está no ar? ({error})
        <div style={{ marginTop: 12 }}>
          <button className="chip" onClick={() => setReloadKey((k) => k + 1)}>TENTAR DE NOVO</button>
        </div>
      </div>
    )
  }
  // gate so no PRIMEIRO load: trocar filtro re-busca sem desmontar a arvore
  // (senao a tela pisca, o scroll se perde e o mapa reseta o viewport)
  if (loading && events.length === 0) {
    return <div className="empty" style={{ paddingTop: 80 }}>CARREGANDO…</div>
  }

  if (isDesktop) {
    return (
      <div style={{ height: '100dvh', display: 'flex', flexDirection: 'column' }}>
        <div className="d-header">
          <span>RADAR★SP</span>
          <nav>
            <span className={tab !== 'locais' ? 'on' : ''} onClick={() => setTab('festas')}>FESTAS</span>
            <span className={tab === 'locais' ? 'on' : ''} onClick={() => setTab('locais')}>LOCAIS</span>
          </nav>
          <span style={{ fontSize: 11 }}>{filtered.length} FESTAS</span>
        </div>
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <div style={{ width: '40%', overflowY: 'auto', borderRight: '3px solid var(--pink)' }}>
            {tab === 'locais' ? locais : festas}
          </div>
          <div style={{ flex: 1 }}>{mapa}</div>
        </div>
        {open && <EventDetail event={open} onClose={() => setOpen(null)} />}
        {sheetOpen && (
          <FilterSheet filters={filters} dispatch={dispatch} count={filtered.length}
                       genreOptions={genreOptions} onClose={() => setSheetOpen(false)} />
        )}
      </div>
    )
  }

  return (
    <div style={{ height: '100dvh' }}>
      {/* mapa SEMPRE montado (display toggle): trocar de aba nao recria o
          contexto GL nem reseta o viewport — o MapLibre re-mede via
          ResizeObserver quando o painel reaparece */}
      <div style={{ position: 'fixed', inset: 0, bottom: 44,
                    display: tab === 'mapa' ? 'block' : 'none' }}>{mapa}</div>
      {tab === 'festas' && <div style={{ height: '100%', overflowY: 'auto' }}>{festas}</div>}
      {tab === 'locais' && locais}
      <BottomTabs tab={tab} onTab={setTab} />
      {open && <EventDetail event={open} onClose={() => setOpen(null)} />}
      {sheetOpen && (
        <FilterSheet filters={filters} dispatch={dispatch} count={filtered.length}
                     genreOptions={genreOptions} onClose={() => setSheetOpen(false)} />
      )}
    </div>
  )
}
