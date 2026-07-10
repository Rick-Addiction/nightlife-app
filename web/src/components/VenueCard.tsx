import type { VenueOut } from '../api/types'
import type { EventWithGeo } from '../data/join'
import { igActivity } from '../data/vivacity'
import { fmtDate } from './EventCard'

export function VenueCard({ venue, upcoming, expanded, onToggle, onOpenEvent, now }: {
  venue: VenueOut; upcoming: EventWithGeo[]; expanded: boolean
  onToggle: () => void; onOpenEvent: (e: EventWithGeo) => void; now?: Date
}) {
  const ig = igActivity(venue.ig_last_post_at, now)
  const n = upcoming.length
  const mapsHref = `https://maps.google.com/?q=${encodeURIComponent(
    `${venue.name} ${venue.address ?? 'São Paulo'}`)}`
  return (
    <div className="b-card" style={{ margin: '8px 12px 0', padding: 10 }} onClick={onToggle}>
      <div className="title" style={{ fontSize: 15 }}>{venue.name}</div>
      <div style={{ marginTop: 5, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {venue.places_verified && <span className="tag ghost">✓ VERIFICADO</span>}
        {ig === 'hoje' && <span className="tag" style={{ background: 'var(--green)' }}>IG HOJE</span>}
        {ig === 'ativo' && <span className="tag ghost" style={{ color: 'var(--green)' }}>IG ATIVO</span>}
        {n > 0 && <span className="tag">{n} {n === 1 ? 'FESTA' : 'FESTAS'}</span>}
        {venue.category && <span className="tag ghost">{venue.category}</span>}
      </div>
      {expanded && (
        <div style={{ marginTop: 8 }} onClick={(e) => e.stopPropagation()}>
          {venue.address && <div className="meta">{venue.address}</div>}
          {upcoming.slice(0, 5).map((e) => (
            <div key={e.id} style={{ fontSize: 11, fontWeight: 700, marginTop: 4, cursor: 'pointer' }}
                 onClick={() => onOpenEvent(e)}>
              <span style={{ color: 'var(--pink)' }}>{fmtDate(e.starts_at)}</span> {e.name}
            </div>
          ))}
          <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
            {venue.instagram && (
              <a className="chip grn" href={`https://instagram.com/${venue.instagram}`}
                 target="_blank" rel="noreferrer">IG</a>
            )}
            {venue.website && (
              <a className="chip" href={venue.website} target="_blank" rel="noreferrer">SITE</a>
            )}
            <a className="chip" href={mapsHref} target="_blank" rel="noreferrer">MAPA</a>
          </div>
        </div>
      )}
    </div>
  )
}
