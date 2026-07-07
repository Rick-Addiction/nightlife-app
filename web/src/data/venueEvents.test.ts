import { describe, it, expect } from 'vitest'
import { upcomingEventsAtVenue } from './venueEvents'
import type { EventWithGeo } from './join'

const ev = (over: Partial<EventWithGeo>): EventWithGeo => ({
  id: 1, name: 'Festa', starts_at: '2026-07-10T23:00:00-03:00', ends_at: null,
  venue_id: 5, status: 'scheduled', genre: null, ticket_url: null, confidence: 40,
  effective_confidence: 40, venueName: 'D-Edge', lat: -23.5, lng: -46.6, mappable: true, ...over,
})

describe('upcomingEventsAtVenue', () => {
  it('filtra pelo venue_id e ordena por data', () => {
    const events = [
      ev({ id: 1, venue_id: 5, starts_at: '2026-07-20T23:00:00-03:00' }),
      ev({ id: 2, venue_id: 9, starts_at: '2026-07-11T23:00:00-03:00' }),
      ev({ id: 3, venue_id: 5, starts_at: '2026-07-10T23:00:00-03:00' }),
    ]
    const out = upcomingEventsAtVenue(events, 5)
    expect(out.map((e) => e.id)).toEqual([3, 1])  // so venue 5, mais cedo primeiro
  })

  it('venue sem eventos vira lista vazia', () => {
    expect(upcomingEventsAtVenue([ev({ venue_id: 1 })], 999)).toEqual([])
  })
})
