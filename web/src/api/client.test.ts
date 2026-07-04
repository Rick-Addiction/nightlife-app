import { describe, it, expect, vi, beforeEach } from 'vitest'
import { buildQuery, fetchEvents } from './client'

describe('buildQuery', () => {
  it('omite campos vazios e serializa os presentes', () => {
    expect(buildQuery({})).toBe('')
    expect(buildQuery({ genre: 'techno', min_confidence: 40 }))
      .toBe('?genre=techno&min_confidence=40')
    expect(buildQuery({ date_from: '2026-06-01', include_past: true }))
      .toBe('?date_from=2026-06-01&include_past=true')
  })
})

describe('fetchEvents', () => {
  beforeEach(() => { vi.restoreAllMocks() })
  it('chama /api/events com a query e devolve o json', async () => {
    const fake = [{ id: 1, name: 'Mamba', status: 'scheduled', confidence: 80, effective_confidence: 80 }]
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(fake), { status: 200 }),
    )
    const out = await fetchEvents({ genre: 'techno' })
    expect(spy).toHaveBeenCalledWith('/api/events?genre=techno')
    expect(out[0].name).toBe('Mamba')
  })
  it('lanca em erro HTTP', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('nope', { status: 500 }))
    await expect(fetchEvents({})).rejects.toThrow()
  })
})
