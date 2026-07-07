import type { EventWithGeo } from './join'

export function upcomingEventsAtVenue(events: EventWithGeo[], venueId: number): EventWithGeo[] {
  return events
    .filter((e) => e.venue_id === venueId)
    .sort((a, b) => (a.starts_at ?? '').localeCompare(b.starts_at ?? ''))
}
