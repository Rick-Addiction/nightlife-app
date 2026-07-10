import type { Dispatch } from 'react'
import type { FilterAction, FilterState, Preset } from '../filters/state'
import type { EventWithGeo } from '../data/join'
import { pickHero } from '../data/hero'
import { EventCard } from '../components/EventCard'
import { FilterChips } from '../components/FilterChips'

const TITLES: Record<Preset, [string, string]> = {
  upcoming: ['PRÓXIMAS', 'FESTAS'],
  today: ['ESTA', 'NOITE'],
  tomorrow: ['AMANHÃ', 'À NOITE'],
  weekend: ['FIM DE', 'SEMANA'],
  all: ['TUDO', 'QUE HÁ'],
}

export function FestasTab({ events, filters, dispatch, onOpen }: {
  events: EventWithGeo[]; filters: FilterState
  dispatch: Dispatch<FilterAction>; onOpen: (e: EventWithGeo) => void
}) {
  const [l1, l2] = TITLES[filters.preset]
  const { hero, rest } = pickHero(events)
  return (
    <div style={{ paddingBottom: 70 }}>
      <div style={{ padding: '14px 12px 4px' }}>
        <div className="hline" style={{ fontSize: 30 }}>
          {l1}<br /><span style={{ color: 'var(--pink)' }}>{l2}</span>
          <br />
          {events.length} FESTAS
        </div>
      </div>
      <FilterChips filters={filters} dispatch={dispatch} />
      {events.length === 0 && <div className="empty">Nenhuma festa com esses filtros.</div>}
      {hero && <EventCard event={hero} variant="hero" onOpen={onOpen} />}
      {rest.map((e) => <EventCard key={e.id} event={e} variant="row" onOpen={onOpen} />)}
    </div>
  )
}
