import type { Feature, Polygon } from 'geojson'
import type { VenueOut } from '../api/types'
import { distanceKm } from '../data/bairros'

// circulo geodesico aproximado (bom o suficiente pra ~5km em SP)
export function circleGeoJSON(lat: number, lng: number, km: number, steps = 64): Feature<Polygon> {
  const ring: [number, number][] = []
  const dLat = km / 110.574
  const dLng = km / (111.32 * Math.cos((lat * Math.PI) / 180))
  for (let i = 0; i < steps; i++) {
    const t = (i / steps) * 2 * Math.PI
    ring.push([lng + dLng * Math.cos(t), lat + dLat * Math.sin(t)])
  }
  ring.push(ring[0])
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } }
}

export function handlesInCircle(venues: VenueOut[], lat: number, lng: number, km: number): number {
  return venues.filter((v) =>
    v.instagram != null && v.lat != null && v.lng != null &&
    distanceKm(lat, lng, v.lat, v.lng) <= km).length
}
