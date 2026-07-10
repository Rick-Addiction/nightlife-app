import { describe, it, expect } from 'vitest'
import { joinEventsWithVenues } from './join'
import type { EventOut, VenueOut } from '../api/types'

const venue = (id: number, name: string, lat: number | null, lng: number | null): VenueOut => ({
  id, name, category: 'nightclub', lat, lng, address: null, instagram: null, website: null,
  status: 'operational', confidence: 50, effective_confidence: 50, is_monitored: false,
})
const ev = (id: number, name: string, venue_id: number | null): EventOut => ({
  id, name, starts_at: '2099-06-13T23:00:00-03:00', ends_at: null, venue_id,
  status: 'scheduled', genre: 'techno', ticket_url: null, flyer_url: null, confidence: 80, effective_confidence: 80,
})

describe('joinEventsWithVenues', () => {
  it('anexa geo do venue quando resolve', () => {
    const out = joinEventsWithVenues([ev(1, 'Mamba', 10)], [venue(10, 'Lab Club', -23.5, -46.6)])
    expect(out[0].venueName).toBe('Lab Club')
    expect(out[0].mappable).toBe(true)
    expect(out[0].lat).toBe(-23.5)
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
})
