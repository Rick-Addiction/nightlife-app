import { useMemo, useState } from 'react'
import type { VenueOut } from '../api/types'
import type { EventWithGeo } from '../data/join'
import { upcomingEventsAtVenue } from '../data/venueEvents'
import { igActivity } from '../data/vivacity'
import { VenueCard } from '../components/VenueCard'

export function normalize(s: string): string {
  return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}

export function filterVenues(venues: VenueOut[], q: string): VenueOut[] {
  const nq = normalize(q.trim())
  if (!nq) return venues
  return venues.filter((v) =>
    normalize(v.name).includes(nq) || (v.address != null && normalize(v.address).includes(nq)))
}

export function LocaisTab({ venues, events, onOpenEvent }: {
  venues: VenueOut[]; events: EventWithGeo[]; onOpenEvent: (e: EventWithGeo) => void
}) {
  const [q, setQ] = useState('')
  const [openId, setOpenId] = useState<number | null>(null)
  const upcomingBy = useMemo(() => {
    const m = new Map<number, EventWithGeo[]>()
    for (const v of venues) m.set(v.id, upcomingEventsAtVenue(events, v.id))
    return m
  }, [venues, events])

  const shown = useMemo(() => {
    const fs = filterVenues(venues, q)
    // vivos primeiro: com festa marcada > IG mais recente > confianca
    return [...fs].sort((a, b) => {
      const fa = (upcomingBy.get(a.id)?.length ?? 0) > 0 ? 1 : 0
      const fb = (upcomingBy.get(b.id)?.length ?? 0) > 0 ? 1 : 0
      if (fa !== fb) return fb - fa
      const ia = igActivity(a.ig_last_post_at) ? 1 : 0
      const ib = igActivity(b.ig_last_post_at) ? 1 : 0
      if (ia !== ib) return ib - ia
      return b.effective_confidence - a.effective_confidence
    })
  }, [venues, q, upcomingBy])

  return (
    <div style={{ height: '100%', overflowY: 'auto', paddingBottom: 70 }}>
      <div style={{ padding: '14px 12px 4px' }}>
        <div className="hline" style={{ fontSize: 30 }}>LOCAIS<br />
          <span style={{ color: 'var(--green)' }}>VIVOS</span></div>
        <div className="label" style={{ marginTop: 5 }}>{shown.length} LOCAIS</div>
      </div>
      <div style={{ padding: '6px 12px' }}>
        <input value={q} onChange={(e) => setQ(e.target.value)}
               placeholder="BUSCAR LOCAL OU RUA"
               style={{ width: '100%', padding: '9px 10px', background: 'var(--panel)',
                        border: '1px solid var(--line)', color: 'var(--text)',
                        fontWeight: 700, fontSize: 13, letterSpacing: '0.04em' }} />
      </div>
      {shown.map((v) => (
        <VenueCard key={v.id} venue={v} upcoming={upcomingBy.get(v.id) ?? []}
                   expanded={openId === v.id}
                   onToggle={() => setOpenId(openId === v.id ? null : v.id)}
                   onOpenEvent={onOpenEvent} />
      ))}
      {shown.length === 0 && <div className="empty">Nenhum local com essa busca.</div>}
    </div>
  )
}
