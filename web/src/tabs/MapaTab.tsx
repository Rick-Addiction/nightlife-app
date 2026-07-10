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
