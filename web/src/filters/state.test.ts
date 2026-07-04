import { describe, it, expect } from 'vitest'
import { initialFilters, filterReducer, queryFromFilters } from './state'

describe('filters', () => {
  it('estado inicial: upcoming, sem genero, confianca 0', () => {
    expect(initialFilters).toEqual({ preset: 'upcoming', genre: null, minConfidence: 0, includePast: false })
  })
  it('reducer atualiza campos', () => {
    const s = filterReducer(initialFilters, { type: 'setGenre', genre: 'techno' })
    expect(s.genre).toBe('techno')
    const s2 = filterReducer(s, { type: 'setMinConfidence', value: 40 })
    expect(s2.minConfidence).toBe(40)
    expect(s2.genre).toBe('techno')
  })
  it('queryFromFilters: upcoming vira query vazia de data (API ja default-futuro)', () => {
    expect(queryFromFilters({ preset: 'upcoming', genre: 'techno', minConfidence: 40, includePast: false }))
      .toEqual({ genre: 'techno', min_confidence: 40 })
  })
  it('queryFromFilters: preset weekend gera date_from/date_to; include_past quando all', () => {
    const q = queryFromFilters({ preset: 'weekend', genre: null, minConfidence: 0, includePast: false }, new Date('2026-06-10T12:00:00'))
    expect(q.date_from).toBeDefined()
    expect(q.date_to).toBeDefined()
    const all = queryFromFilters({ preset: 'all', genre: null, minConfidence: 0, includePast: true })
    expect(all.include_past).toBe(true)
  })
})
