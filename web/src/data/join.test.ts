import { describe, it, expect } from 'vitest'
import { joinEventsWithVenues } from './join'
import type { EventOut, VenueOut } from '../api/types'

const venue = (id: number, name: string, lat: number | null, lng: number | null, instagram: string | null = null): VenueOut => ({
  id, name, category: 'nightclub', lat, lng, address: null, instagram, website: null,
  status: 'operational', confidence: 50, effective_confidence: 50, is_monitored: false,
  ig_last_post_at: null, places_verified: false,
})
const ev = (id: number, name: string, venue_id: number | null): EventOut => ({
  id, name, starts_at: '2099-06-13T23:00:00-03:00', ends_at: null, venue_id,
  status: 'scheduled', genre: 'techno', ticket_url: null, flyer_url: null, confidence: 80, effective_confidence: 80,
})

describe('joinEventsWithVenues', () => {
  it('anexa geo do venue quando resolve', () => {
    const out = joinEventsWithVenues([ev(1, 'Mamba', 10)], [venue(10, 'Lab Club', -23.5, -46.6, 'labclub')])
    expect(out[0].venueName).toBe('Lab Club')
    expect(out[0].mappable).toBe(true)
    expect(out[0].lat).toBe(-23.5)
    expect(out[0].venueInstagram).toBe('labclub')
  })
  it('evento sem venue_id -> nao mapeavel, mas presente', () => {
    const out = joinEventsWithVenues([ev(1, 'Festa', null)], [])
    expect(out[0].mappable).toBe(false)
    expect(out[0].venueName).toBeNull()
  })
  it('venue sem geo -> nao mapeavel', () => {
    const out = joinEventsWithVenues([ev(1, 'Festa', 10)], [venue(10, 'Cargo', null, null)])
    expect(out[0].mappable).toBe(false)
    expect(out[0].venueName).toBe('Cargo')  // nome resolve mesmo sem geo
  })
  it('propaga ig_last_post_at do venue para o evento joinado', () => {
    const v = { ...venue(7, 'Lab Club', -23.5, -46.6), ig_last_post_at: '2026-07-09T03:00:00Z' }
    const out = joinEventsWithVenues([ev(1, 'Mamba', 7)], [v])
    expect(out[0].venueIgLastPostAt).toBe('2026-07-09T03:00:00Z')
  })
  it('evento sem venue tem venueIgLastPostAt null', () => {
    const out = joinEventsWithVenues([ev(1, 'Festa', null)], [])
    expect(out[0].venueIgLastPostAt).toBeNull()
  })
})
