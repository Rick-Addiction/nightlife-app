import { describe, it, expect } from 'vitest'
import { circleGeoJSON, handlesInCircle } from './sweep'
import type { VenueOut } from '../api/types'

function venue(id: number, lat: number | null, lng: number | null, ig: string | null): VenueOut {
  return { id, name: `V${id}`, category: null, lat, lng, address: null, instagram: ig,
           website: null, status: 'active', confidence: 50, effective_confidence: 50,
           is_monitored: false, ig_last_post_at: null, places_verified: false }
}

describe('circleGeoJSON', () => {
  it('gera poligono fechado com steps+1 pontos em volta do centro', () => {
    const f = circleGeoJSON(-23.553, -46.656, 2, 32)
    expect(f.geometry.type).toBe('Polygon')
    const ring = f.geometry.coordinates[0]
    expect(ring).toHaveLength(33)
    expect(ring[0]).toEqual(ring[32])   // fechado
    // raio ~2km: todo ponto entre 1.9 e 2.1 km do centro (haversine simples)
    for (const [lng, lat] of ring.slice(0, 32)) {
      const R = 6371, rad = (x: number) => (x * Math.PI) / 180
      const dLat = rad(lat - -23.553), dLng = rad(lng - -46.656)
      const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(-23.553)) * Math.cos(rad(lat)) * Math.sin(dLng / 2) ** 2
      const d = 2 * R * Math.asin(Math.sqrt(h))
      expect(d).toBeGreaterThan(1.9)
      expect(d).toBeLessThan(2.1)
    }
  })
})

describe('handlesInCircle', () => {
  it('conta so venues com instagram e geo dentro do raio', () => {
    const vs = [
      venue(1, -23.552, -46.652, 'blitzhaus'),   // dentro (~450m)
      venue(2, -23.52, -46.666, 'dedge'),        // fora (~3.8km)
      venue(3, -23.553, -46.656, null),          // sem IG
      venue(4, null, null, 'semgeo'),            // sem geo
    ]
    expect(handlesInCircle(vs, -23.553, -46.656, 2)).toBe(1)
  })
})
