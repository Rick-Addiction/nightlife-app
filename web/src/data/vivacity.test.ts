import { describe, it, expect } from 'vitest'
import { igActivity, venueIdsWithEventToday, IG_ACTIVE_DAYS } from './vivacity'
import type { EventWithGeo } from './join'

const NOW = new Date(2026, 6, 10, 22, 0) // 10/07/2026 22h local

function evt(venueId: number | null, startsAt: string | null): EventWithGeo {
  return {
    id: Math.random(), name: 'x', starts_at: startsAt, ends_at: null,
    venue_id: venueId, status: 'scheduled', genre: null, ticket_url: null,
    flyer_url: null, confidence: 50, effective_confidence: 50,
    venueName: null, venueInstagram: null, venueIgLastPostAt: null,
    lat: null, lng: null, mappable: false,
  } as EventWithGeo
}

describe('igActivity', () => {
  it('post no mesmo dia local = hoje', () => {
    expect(igActivity(new Date(2026, 6, 10, 8, 0).toISOString(), NOW)).toBe('hoje')
  })
  it('post recente (<= 30d) = ativo', () => {
    expect(igActivity(new Date(2026, 5, 20).toISOString(), NOW)).toBe('ativo')
    expect(IG_ACTIVE_DAYS).toBe(30)
  })
  it('post velho (> 30d), null e lixo = null', () => {
    expect(igActivity(new Date(2026, 3, 1).toISOString(), NOW)).toBeNull()
    expect(igActivity(null, NOW)).toBeNull()
    expect(igActivity('nao-e-data', NOW)).toBeNull()
  })
})

describe('venueIdsWithEventToday', () => {
  it('so venues com starts_at no dia local de hoje', () => {
    const hoje = evt(1, new Date(2026, 6, 10, 23, 30).toISOString())
    const amanha = evt(2, new Date(2026, 6, 11, 1, 0).toISOString())
    const semData = evt(3, null)
    const semVenue = evt(null, new Date(2026, 6, 10, 23, 0).toISOString())
    const ids = venueIdsWithEventToday([hoje, amanha, semData, semVenue], NOW)
    expect(ids.has(1)).toBe(true)
    expect(ids.has(2)).toBe(false)
    expect(ids.has(3)).toBe(false)
    expect(ids.size).toBe(1)
  })
})
