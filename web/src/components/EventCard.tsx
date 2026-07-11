import type { EventWithGeo } from '../data/join'

export function fmtDate(iso: string | null): string {
  if (!iso) return 'data a confirmar'
  const d = new Date(iso)
  return d.toLocaleString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    .toUpperCase()
}

export function EventCard({ event, variant, onOpen }: {
  event: EventWithGeo; variant: 'hero' | 'row'; onOpen: (e: EventWithGeo) => void
}) {
  const meta = `${fmtDate(event.starts_at)}${event.venueName ? ` → ${event.venueName}` : ''}`
  if (variant === 'hero') {
    return (
      <div className="b-card hot" onClick={() => onOpen(event)} style={{ margin: '8px 12px 0' }}>
        {event.flyer_url && (
          <img src={event.flyer_url} alt={event.name}
               style={{ width: '100%', height: 190, objectFit: 'cover', display: 'block',
                        borderBottom: '2px solid var(--pink)' }} />
        )}
        <div style={{ padding: 10 }}>
          <div className="title" style={{ fontSize: 19 }}>{event.name}</div>
          <div className="meta">{meta}</div>
          <div style={{ marginTop: 7 }}>
            {!event.starts_at && <span className="tag ghost">DATA A CONFIRMAR</span>}
            {event.genre && <span className="tag">{event.genre}</span>}
            {event.ticket_url && <span className="tag ghost">ticket</span>}
          </div>
        </div>
        <span className="conf">{event.effective_confidence}</span>
      </div>
    )
  }
  return (
    <div className="b-card" onClick={() => onOpen(event)}
         style={{ margin: '8px 12px 0', padding: 9, display: 'flex', gap: 10, alignItems: 'center' }}>
      {event.flyer_url && (
        <img src={event.flyer_url} alt={event.name} loading="lazy" decoding="async"
             style={{ width: 46, height: 46, objectFit: 'cover', flex: 'none' }} />
      )}
      <div style={{ minWidth: 0 }}>
        <div className="title">{event.name}</div>
        <div className="meta">{meta}{!event.mappable && ' · LOCAL A CONFIRMAR'}</div>
        {!event.starts_at && <span className="tag ghost">DATA A CONFIRMAR</span>}
      </div>
      <span className="conf">{event.effective_confidence}</span>
    </div>
  )
}
