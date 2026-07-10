import { describe, it, expect } from 'vitest'
import { pickHero } from './hero'
import type { EventWithGeo } from './join'

const ev = (id: number, flyer: string | null): EventWithGeo => ({
  id, name: `E${id}`, starts_at: '2099-07-12T23:00:00-03:00', ends_at: null,
  venue_id: 1, status: 'scheduled', genre: null, ticket_url: null, confidence: 50,
  effective_confidence: 50, flyer_url: flyer, venueName: null, venueInstagram: null, venueIgLastPostAt: null, lat: null, lng: null, mappable: false,
})

describe('pickHero', () => {
  it('primeiro evento COM flyer vira hero; resto preserva a ordem', () => {
    const { hero, rest } = pickHero([ev(1, null), ev(2, '/f/2.jpg'), ev(3, '/f/3.jpg')])
    expect(hero?.id).toBe(2)
    expect(rest.map((e) => e.id)).toEqual([1, 3])
  })
  it('sem flyers: sem hero, tudo em rest', () => {
    const { hero, rest } = pickHero([ev(1, null), ev(2, null)])
    expect(hero).toBeNull()
    expect(rest.map((e) => e.id)).toEqual([1, 2])
  })
})
