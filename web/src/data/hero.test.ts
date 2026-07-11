import { describe, it, expect } from 'vitest'
import { pickHero } from './hero'
import type { EventWithGeo } from './join'

const ev = (id: number, flyer: string | null, startsAt: string | null = '2099-07-12T23:00:00-03:00'): EventWithGeo => ({
  id, name: `E${id}`, starts_at: startsAt, ends_at: null,
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
  it('hero prefere evento COM data; sem-data so vira hero se nao houver outro com flyer', () => {
    const semData = ev(1, '/f/a.jpg', null)
    const comData = ev(2, '/f/b.jpg', '2026-07-18T02:00:00Z')
    expect(pickHero([semData, comData]).hero?.id).toBe(2)
    expect(pickHero([semData]).hero?.id).toBe(1)
  })
})
