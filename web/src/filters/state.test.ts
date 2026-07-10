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
  it('datas usam o dia LOCAL (nao UTC) mesmo a noite — app noturno', () => {
    // sab 04/07/2026 21h no fuso LOCAL do host (independe do TZ do runner)
    const evening = new Date(2026, 6, 4, 21, 0, 0)
    const hoje = queryFromFilters({ preset: 'today', genre: null, minConfidence: 0, includePast: false }, evening)
    expect(hoje.date_from).toBe('2026-07-04')
    expect(hoje.date_to).toBe('2026-07-04')
    const wknd = queryFromFilters({ preset: 'weekend', genre: null, minConfidence: 0, includePast: false }, evening)
    expect(wknd.date_from).toBe('2026-07-10') // proxima sexta
    expect(wknd.date_to).toBe('2026-07-12')   // domingo
  })
})

describe('preset tomorrow', () => {
  it('gera date_from/date_to de amanha (calendario local)', () => {
    const now = new Date(2026, 6, 10, 22, 0)   // 10/07/2026 22h local
    const q = queryFromFilters({ ...initialFilters, preset: 'tomorrow' }, now)
    expect(q.date_from).toBe('2026-07-11')
    expect(q.date_to).toBe('2026-07-11')
  })
})
