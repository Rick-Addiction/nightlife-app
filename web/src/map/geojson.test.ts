import { describe, it, expect } from 'vitest'
import { venuesToFeatureCollection } from './geojson'
import type { VenueOut } from '../api/types'

const venue = (over: Partial<VenueOut>): VenueOut => ({
  id: 1, name: 'X', category: 'nightclub', lat: -23.5, lng: -46.6, address: null,
  instagram: null, website: null, status: 'operational', confidence: 50,
  effective_confidence: 50, is_monitored: false, ig_last_post_at: null, places_verified: false, ...over,
})

describe('venuesToFeatureCollection', () => {
  it('mapeia venue com geo para Feature com coords [lng, lat] e props', () => {
    const fc = venuesToFeatureCollection([venue({ id: 7, name: 'D-Edge', lat: -23.53, lng: -46.66 })])
    expect(fc.features).toHaveLength(1)
    const f = fc.features[0]
    expect(f.geometry.coordinates).toEqual([-46.66, -23.53])
    expect(f.properties).toMatchObject({ id: 7, name: 'D-Edge', category: 'nightclub' })
  })

  it('pula venues sem geo', () => {
    const fc = venuesToFeatureCollection([venue({ lat: null }), venue({ lng: null }), venue({ id: 9 })])
    expect(fc.features).toHaveLength(1)
    expect(fc.features[0].properties!.id).toBe(9)
  })

  it('lista vazia vira FeatureCollection vazia', () => {
    expect(venuesToFeatureCollection([]).features).toEqual([])
  })
})
