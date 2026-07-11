import { useEffect, useRef, useState } from 'react'
import type { Dispatch } from 'react'
import { MapView } from '../map/MapView'
import { Drawer } from '../components/Drawer'
import type { DrawerState } from '../components/drawerSnap'
import { EventCard } from '../components/EventCard'
import { FilterChips } from '../components/FilterChips'
import { SweepPanel, type SweepMode } from '../components/SweepPanel'
import { SweepReport } from '../components/SweepReport'
import { venueIdsWithEventToday } from '../data/vivacity'
import type { EventWithGeo } from '../data/join'
import type { VenueOut } from '../api/types'
import type { FilterAction, FilterState } from '../filters/state'
import { fetchCurrentSweep, startSweep, type SweepOut } from '../api/sweep'
import { handlesInCircle } from '../map/sweep'

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
                          onOpenSheet, activeCount, withDrawer, onDataStale }: {
  events: EventWithGeo[]; venues: VenueOut[]
  filters: FilterState; dispatch: Dispatch<FilterAction>
  selectedId: number | null; onSelect: (id: number) => void
  onOpenSheet: () => void; activeCount: number; withDrawer: boolean
  onDataStale: () => void
}) {
  const [layers, setLayers] = useState<Layers>({ festas: true, locais: true, hojeOnly: false })
  const [panel, setPanel] = useState(false)
  const [drawer, setDrawer] = useState<DrawerState>('closed')
  const [sweepUi, setSweepUi] = useState<SweepMode>('idle')
  const [sweep, setSweep] = useState<SweepOut | null>(null)
  const [reportOpen, setReportOpen] = useState(false)
  const [postError, setPostError] = useState<string | null>(null)

  // poll do sweep corrente enquanto rodando; ao terminar, dispara onDataStale
  // pro App rebuscar eventos/venues (o sweep pode ter criado festas/pins novos)
  const sweepRef = useRef(sweep)
  useEffect(() => { sweepRef.current = sweep }, [sweep])
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const s = await fetchCurrentSweep()
        if (!alive) return
        setSweep((prev) => {
          if (prev?.status === 'running' && s.status !== 'running') onDataStale()
          return s
        })
      } catch { /* 404 = nunca varreu; silencio */ }
    }
    tick()
    const id = setInterval(() => {
      // poll continuo so enquanto ha run ativo (ou aguardando o 1o status)
      if (sweepRef.current?.status === 'running') tick()
    }, 5000)
    return () => { alive = false; clearInterval(id) }
  }, [onDataStale])

  const count = typeof sweepUi === 'object'
    ? handlesInCircle(venues, sweepUi.lat, sweepUi.lng, sweepUi.km) : 0

  return (
    <div style={{ position: 'relative', height: '100%' }}>
      <MapView events={layers.festas ? events : []}
               venues={visibleVenues(venues, events, layers)}
               selectedId={selectedId} onSelect={onSelect} showVenues={layers.locais}
               onPickPoint={sweepUi === 'picking'
                 ? (lat, lng) => setSweepUi({ lat, lng, km: 2 }) : undefined}
               circle={typeof sweepUi === 'object' ? sweepUi : null} />

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
        <button className={`chip${sweepUi !== 'idle' ? ' on' : ''}`}
                onClick={() => setSweepUi(sweepUi === 'idle' ? 'picking' : 'idle')}>
          ⌖ VARRER ÁREA
        </button>
      </div>

      {typeof sweepUi === 'object' && postError && (
        <div style={{ position: 'absolute', left: 10, right: 10, bottom: 168, zIndex: 15,
                      color: 'var(--pink)', fontSize: 11, fontWeight: 700 }}>
          {postError}
        </div>
      )}

      <SweepPanel mode={sweepUi} count={count} sweep={sweep}
                  onConfirm={async () => {
                    if (typeof sweepUi !== 'object') return
                    const c = sweepUi
                    setPostError(null)
                    try {
                      await startSweep(c.lat, c.lng, c.km)
                      setSweepUi('idle')
                      setSweep((s) => s ? { ...s, status: 'running', phase: 'iniciando',
                                            done_handles: 0, total_handles: 0, diff: null } : s)
                      const first = await fetchCurrentSweep().catch(() => null)
                      if (first) setSweep(first)
                    } catch (e) {
                      setPostError(String(e instanceof Error ? e.message : e))
                    }
                  }}
                  onCancel={() => {
                    setSweepUi('idle')
                    setPostError(null)
                    setSweep((s) => s && s.status !== 'running' ? null : s)
                  }}
                  onKm={(km) => setSweepUi((m) => typeof m === 'object' ? { ...m, km } : m)}
                  onOpenReport={() => setReportOpen(true)} />

      {reportOpen && sweep && <SweepReport sweep={sweep} onClose={() => setReportOpen(false)} />}

      {withDrawer && (
        <Drawer state={drawer} onState={setDrawer}
                label={`${events.length} ${events.length === 1 ? 'FESTA' : 'FESTAS'} NA ÁREA`}>
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
