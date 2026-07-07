import type { EventWithGeo } from './join'

export function upcomingEventsAtVenue(events: EventWithGeo[], venueId: number): EventWithGeo[] {
  return events
    .filter((e) => e.venue_id === venueId)
    .sort((a, b) => {
      // eventos sem data vao para o fim (nao para o topo da lista "futuros")
      if (a.starts_at == null) return b.starts_at == null ? 0 : 1
      if (b.starts_at == null) return -1
      return a.starts_at.localeCompare(b.starts_at)
    })
}
