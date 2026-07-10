import { describe, it, expect } from 'vitest'
import { initialFilters, filterReducer, queryFromFilters, activeFilterCount } from './state'

describe('filters', () => {
  it('estado inicial', () => {
    expect(initialFilters).toEqual({
      preset: 'upcoming', date: null, genres: [], minConfidence: 0, includePast: false,
      bairro: null, nearMe: null, extras: { ticket: false, flyer: false, igAtivo: false },
    })
  })
  it('toggleGenre acumula e remove (multi)', () => {
    const a = filterReducer(initialFilters, { type: 'toggleGenre', genre: 'techno' })
    const b = filterReducer(a, { type: 'toggleGenre', genre: 'funk' })
    expect(b.genres).toEqual(['techno', 'funk'])
    expect(filterReducer(b, { type: 'toggleGenre', genre: 'techno' }).genres).toEqual(['funk'])
  })
  it('bairro e nearMe sao mutuamente exclusivos', () => {
    const comBairro = filterReducer(initialFilters, { type: 'setBairro', bairro: 'AUGUSTA' })
    const comGps = filterReducer(comBairro, { type: 'setNearMe', point: { lat: -23.55, lng: -46.66 } })
    expect(comGps.bairro).toBeNull()
    expect(comGps.nearMe).toEqual({ lat: -23.55, lng: -46.66 })
    expect(filterReducer(comGps, { type: 'setBairro', bairro: 'LAPA' }).nearMe).toBeNull()
  })
  it('toggleExtra liga/desliga sem afetar os irmaos', () => {
    const s = filterReducer(initialFilters, { type: 'toggleExtra', key: 'flyer' })
    expect(s.extras).toEqual({ ticket: false, flyer: true, igAtivo: false })
    expect(filterReducer(s, { type: 'toggleExtra', key: 'flyer' }).extras.flyer).toBe(false)
  })
  it('setDate seta preset=date; setPreset limpa a data', () => {
    const s = filterReducer(initialFilters, { type: 'setDate', date: '2026-07-18' })
    expect(s.preset).toBe('date')
    expect(s.date).toBe('2026-07-18')
    const volta = filterReducer(s, { type: 'setPreset', preset: 'today' })
    expect(volta.date).toBeNull()
  })
  it('clearAll volta ao inicial', () => {
    let s = filterReducer(initialFilters, { type: 'setBairro', bairro: 'AUGUSTA' })
    s = filterReducer(s, { type: 'toggleGenre', genre: 'techno' })
    expect(filterReducer(s, { type: 'clearAll' })).toEqual(initialFilters)
  })
  it('activeFilterCount conta dimensoes ativas', () => {
    expect(activeFilterCount(initialFilters)).toBe(0)
    let s = filterReducer(initialFilters, { type: 'toggleGenre', genre: 'techno' })
    s = filterReducer(s, { type: 'toggleGenre', genre: 'funk' })   // genres = 1 dimensao
    s = filterReducer(s, { type: 'setBairro', bairro: 'AUGUSTA' })
    s = filterReducer(s, { type: 'toggleExtra', key: 'ticket' })
    s = filterReducer(s, { type: 'setMinConfidence', value: 40 })
    expect(activeFilterCount(s)).toBe(4)
  })
})

describe('queryFromFilters', () => {
  it('genero NAO vai mais pra API (filtro client-side)', () => {
    const s = filterReducer(initialFilters, { type: 'toggleGenre', genre: 'techno' })
    expect(queryFromFilters({ ...s, minConfidence: 40 })).toEqual({ min_confidence: 40 })
  })
  it('preset date vira date_from=date_to', () => {
    const s = filterReducer(initialFilters, { type: 'setDate', date: '2026-07-18' })
    const q = queryFromFilters(s)
    expect(q.date_from).toBe('2026-07-18')
    expect(q.date_to).toBe('2026-07-18')
  })
  it('datas locais dos presets preservadas (regressao C-1)', () => {
    const evening = new Date(2026, 6, 4, 21, 0, 0)
    const hoje = queryFromFilters({ ...initialFilters, preset: 'today' }, evening)
    expect(hoje.date_from).toBe('2026-07-04')
    const wknd = queryFromFilters({ ...initialFilters, preset: 'weekend' }, evening)
    expect(wknd.date_from).toBe('2026-07-10')
    expect(wknd.date_to).toBe('2026-07-12')
    const amanha = queryFromFilters({ ...initialFilters, preset: 'tomorrow' }, evening)
    expect(amanha.date_from).toBe('2026-07-05')
    expect(queryFromFilters({ ...initialFilters, preset: 'all', includePast: true }).include_past).toBe(true)
  })
})
