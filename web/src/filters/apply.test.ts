import { describe, it, expect } from 'vitest'
import { applyClientFilters, NEAR_ME_KM } from './apply'
import { initialFilters } from './state'
import type { EventWithGeo } from '../data/join'

const NOW = new Date(2026, 6, 10, 22, 0)

let seq = 0
function evt(over: Partial<EventWithGeo>): EventWithGeo {
  return {
    id: ++seq, name: 'x', starts_at: null, ends_at: null, venue_id: 1,
    status: 'scheduled', genre: null, ticket_url: null, flyer_url: null,
    confidence: 50, effective_confidence: 50, venueName: null,
    venueInstagram: null, venueIgLastPostAt: null,
    lat: null, lng: null, mappable: false, ...over,
  } as EventWithGeo
}

describe('applyClientFilters', () => {
  it('sem filtros ativos devolve tudo', () => {
    const evs = [evt({}), evt({ genre: 'techno' })]
    expect(applyClientFilters(evs, initialFilters, NOW)).toHaveLength(2)
  })
  it('genres multi: casa qualquer um; evento sem genero cai fora', () => {
    const evs = [evt({ genre: 'techno' }), evt({ genre: 'funk' }), evt({ genre: 'rock' }), evt({})]
    const f = { ...initialFilters, genres: ['techno', 'funk'] }
    expect(applyClientFilters(evs, f, NOW).map((e) => e.genre)).toEqual(['techno', 'funk'])
  })
  it('bairro classifica por lat/lng; sem geo cai fora', () => {
    const vilaMad = evt({ lat: -23.556, lng: -46.69, mappable: true })
    const tatuape = evt({ lat: -23.54, lng: -46.576, mappable: true })
    const semGeo = evt({})
    const f = { ...initialFilters, bairro: 'VILA MADALENA' }
    expect(applyClientFilters([vilaMad, tatuape, semGeo], f, NOW)).toEqual([vilaMad])
  })
  it('nearMe: raio de NEAR_ME_KM', () => {
    const perto = evt({ lat: -23.556, lng: -46.69, mappable: true })
    const longe = evt({ lat: -23.54, lng: -46.576, mappable: true }) // Tatuape, ~12km
    const f = { ...initialFilters, nearMe: { lat: -23.556, lng: -46.692 } }
    expect(applyClientFilters([perto, longe], f, NOW)).toEqual([perto])
    expect(NEAR_ME_KM).toBe(3)
  })
  it('extras: ticket, flyer e igAtivo', () => {
    const full = evt({ ticket_url: 't', flyer_url: 'f', venueIgLastPostAt: new Date(2026, 6, 9).toISOString() })
    const pelado = evt({})
    const fT = { ...initialFilters, extras: { ticket: true, flyer: false, igAtivo: false } }
    const fF = { ...initialFilters, extras: { ticket: false, flyer: true, igAtivo: false } }
    const fIG = { ...initialFilters, extras: { ticket: false, flyer: false, igAtivo: true } }
    expect(applyClientFilters([full, pelado], fT, NOW)).toEqual([full])
    expect(applyClientFilters([full, pelado], fF, NOW)).toEqual([full])
    expect(applyClientFilters([full, pelado], fIG, NOW)).toEqual([full])
  })
})
