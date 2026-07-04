import type { EventWithGeo } from '../data/join'
import { EventCard } from './EventCard'

export function EventList({ events, selectedId, onSelect }: {
  events: EventWithGeo[]; selectedId: number | null; onSelect: (id: number) => void
}) {
  if (events.length === 0) return <div className="empty">Nenhum evento com esses filtros.</div>
  return (
    <div>
      {events.map((e) => (
        <EventCard key={e.id} event={e} selected={e.id === selectedId} onSelect={onSelect} />
      ))}
    </div>
  )
}
