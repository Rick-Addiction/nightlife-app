import { describe, it, expect } from 'vitest'
import { BAIRROS, CLASSIFY_MAX_KM, classify, distanceKm } from './bairros'

describe('bairros', () => {
  it('distanceKm: mesmo ponto = 0; Augusta -> Vila Madalena ~3-4km', () => {
    expect(distanceKm(-23.553, -46.656, -23.553, -46.656)).toBe(0)
    const d = distanceKm(-23.553, -46.656, -23.556, -46.69)
    expect(d).toBeGreaterThan(3)
    expect(d).toBeLessThan(4)
  })
  it('classify: em cima do centroide devolve o bairro', () => {
    for (const b of BAIRROS) {
      expect(classify(b.lat, b.lng)).not.toBeNull()
    }
    expect(classify(-23.556, -46.69)).toBe('VILA MADALENA')
  })
  it('classify: longe de tudo devolve null', () => {
    expect(classify(-22.9, -43.2)).toBeNull() // Rio
    expect(classify(-23.553, -46.9)).toBeNull() // Osasco
  })
  it('classify: dentro do raio-limite classifica', () => {
    expect(classify(-23.547, -46.69)).toBe('VILA MADALENA') // ~1km ao norte
    expect(CLASSIFY_MAX_KM).toBe(2)
  })
})
