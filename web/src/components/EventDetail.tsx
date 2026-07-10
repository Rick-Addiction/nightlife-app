import type { EventWithGeo } from '../data/join'
import { fmtDate } from './EventCard'

export function EventDetail({ event, onClose }: {
  event: EventWithGeo; onClose: () => void
}) {
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(0,0,0,.75)' }}
         onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           style={{ position: 'absolute', bottom: 0, left: 0, right: 0, maxWidth: 560,
                    margin: '0 auto', background: 'var(--black)', borderTop: '3px solid var(--pink)',
                    maxHeight: '92vh', overflowY: 'auto' }}>
        {/* sticky: com flyer alto + sheet rolada, o X nao pode fugir da tela */}
        <button onClick={onClose} aria-label="fechar"
                style={{ position: 'sticky', top: 8, float: 'right', marginRight: 8, zIndex: 2,
                         background: 'var(--black)', color: 'var(--text)',
                         border: '2px solid var(--line)', fontWeight: 900,
                         width: 34, height: 34, cursor: 'pointer' }}>✕</button>
        {event.flyer_url && (
          <img src={event.flyer_url} alt={event.name}
               style={{ width: '100%', maxHeight: 340, objectFit: 'cover', display: 'block',
                        borderBottom: '3px solid var(--pink)' }} />
        )}
        <div style={{ padding: '12px 14px 90px' }}>
          <div className="hline" style={{ fontSize: 24 }}>{event.name}</div>
          <div style={{ color: 'var(--green)', fontWeight: 800, fontSize: 12, marginTop: 6 }}>
            {fmtDate(event.starts_at)}
          </div>
          {event.venueName && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text)', fontWeight: 700 }}>
              📍 {event.venueName}
            </div>
          )}
          <div style={{ marginTop: 10 }}>
            {event.genre && <span className="tag">{event.genre}</span>}
            <span className="tag ghost">CONF {event.effective_confidence}</span>
          </div>
        </div>
        <div style={{ position: 'sticky', bottom: 0, display: 'flex', gap: 4, padding: '10px 12px',
                      background: 'var(--black)', borderTop: '2px solid var(--line)' }}>
          {event.ticket_url && (
            <a className="b-btn primary" style={{ flex: 2 }} href={event.ticket_url}
               target="_blank" rel="noreferrer">TICKET →</a>
          )}
          {event.venueInstagram && (
            <a className="b-btn" style={{ flex: 1 }} href={`https://instagram.com/${event.venueInstagram}`}
               target="_blank" rel="noreferrer">IG</a>
          )}
          {event.mappable && event.lat != null && event.lng != null && (
            <a className="b-btn" style={{ flex: 1 }} href={`https://maps.google.com/?q=${event.lat},${event.lng}`}
               target="_blank" rel="noreferrer">MAPA</a>
          )}
        </div>
      </div>
    </div>
  )
}
