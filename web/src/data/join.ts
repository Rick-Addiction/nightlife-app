import type { EventOut, VenueOut } from '../api/types'

export interface EventWithGeo extends EventOut {
  venueName: string | null
  venueInstagram: string | null
  venueIgLastPostAt: string | null
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
      venueInstagram: v?.instagram ?? null,
      venueIgLastPostAt: v?.ig_last_post_at ?? null,
      lat,
      lng,
      mappable: lat != null && lng != null,
    }
  })
}
