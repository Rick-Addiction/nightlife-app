import { useEffect, useReducer, useState } from 'react'
import './theme.css'
import { fetchEvents, fetchVenues } from './api/client'
import type { VenueOut } from './api/types'
import { joinEventsWithVenues, type EventWithGeo } from './data/join'
import { filterReducer, initialFilters, queryFromFilters } from './filters/state'
import { FestasTab } from './tabs/FestasTab'
import { MapView } from './map/MapView'
import { BottomTabs, type Tab } from './components/BottomTabs'
import { EventDetail } from './components/EventDetail'

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
  const [showVenues] = useState(true)
  const [open, setOpen] = useState<EventWithGeo | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const isDesktop = useIsDesktop()

  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    Promise.all([fetchEvents(queryFromFilters(filters)), fetchVenues()])
      .then(([evs, vns]) => { if (alive) { setEvents(joinEventsWithVenues(evs, vns)); setVenues(vns) } })
      .catch((e) => { if (alive) setError(String(e)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [filters, reloadKey])

  const openEvent = (e: EventWithGeo) => { setOpen(e); setSelectedId(e.id) }

  const mapa = (
    <MapView events={events} venues={venues} selectedId={selectedId}
             onSelect={(id) => { const e = events.find((x) => x.id === id); if (e) openEvent(e) }}
             showVenues={showVenues} />
  )
  const festas = <FestasTab events={events} filters={filters} dispatch={dispatch} onOpen={openEvent} />
  const locais = <div className="empty" style={{ paddingTop: 80 }}>LOCAIS — em breve (Plano C-2)</div>

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
          <span style={{ fontSize: 11 }}>{events.length} FESTAS</span>
        </div>
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <div style={{ width: '40%', overflowY: 'auto', borderRight: '3px solid var(--pink)' }}>
            {tab === 'locais' ? locais : festas}
          </div>
          <div style={{ flex: 1 }}>{mapa}</div>
        </div>
        {open && <EventDetail event={open} onClose={() => setOpen(null)} />}
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
    </div>
  )
}
