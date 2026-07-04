import type { EventWithGeo } from '../data/join'

function fmtDate(iso: string | null): string {
  if (!iso) return 'data a confirmar'
  const d = new Date(iso)
  return d.toLocaleString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function EventCard({ event, selected, onSelect }: {
  event: EventWithGeo; selected: boolean; onSelect: (id: number) => void
}) {
  return (
    <div className={`evcard${selected ? ' sel' : ''}`} onClick={() => onSelect(event.id)}>
      <span className="conf">{event.effective_confidence}</span>
      <div className="name">{event.name}</div>
      <div className="meta">
        {fmtDate(event.starts_at)}
        {event.venueName ? ` · ${event.venueName}` : ''}
        {!event.mappable && <span className="nogeo"> · local a confirmar</span>}
      </div>
      <div>
        {event.genre && <span className="tag">{event.genre}</span>}
        {event.ticket_url && <span className="tag">ticket</span>}
      </div>
    </div>
  )
}
