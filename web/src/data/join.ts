import type { EventOut, VenueOut } from '../api/types'

export interface EventWithGeo extends EventOut {
  venueName: string | null
  lat: number | null
  lng: number | null
  mappable: boolean
}

export function joinEventsWithVenues(events: EventOut[], venues: VenueOut[]): EventWithGeo[] {
  const byId = new Map(venues.map((v) => [v.id, v]))
  return events.map((e) => {
    const v = e.venue_id != null ? byId.get(e.venue_id) : undefined
    const lat = v?.lat ?? null
    const lng = v?.lng ?? null
    return {
      ...e,
      venueName: v?.name ?? null,
      lat,
      lng,
      mappable: lat != null && lng != null,
    }
  })
}
