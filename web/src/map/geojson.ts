import type { FeatureCollection, Point } from 'geojson'
import type { VenueOut } from '../api/types'

export function venuesToFeatureCollection(venues: VenueOut[]): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: venues
      .filter((v) => v.lat != null && v.lng != null)
      .map((v) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [v.lng!, v.lat!] },
        properties: { id: v.id, name: v.name, category: v.category },
      })),
  }
}
