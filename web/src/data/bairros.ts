// Centroides = sementes do discover_places (ingestion/places_source.py),
// com nomes de exibicao; as duas sementes da Augusta viram uma so.
export interface Bairro { name: string; lat: number; lng: number }

export const BAIRROS: Bairro[] = [
  { name: 'AUGUSTA', lat: -23.553, lng: -46.656 },
  { name: 'VILA MADALENA', lat: -23.556, lng: -46.69 },
  { name: 'BARRA FUNDA', lat: -23.526, lng: -46.664 },
  { name: 'LAPA', lat: -23.523, lng: -46.705 },
  { name: 'ITAIM / V. OLÍMPIA', lat: -23.585, lng: -46.679 },
  { name: 'PINHEIROS', lat: -23.567, lng: -46.695 },
  { name: 'CENTRO', lat: -23.544, lng: -46.642 },
  { name: 'BEXIGA', lat: -23.558, lng: -46.645 },
  { name: 'VILA MARIANA', lat: -23.589, lng: -46.634 },
  { name: 'MOEMA', lat: -23.6, lng: -46.665 },
  { name: 'SANTANA', lat: -23.503, lng: -46.625 },
  { name: 'TATUAPÉ', lat: -23.54, lng: -46.576 },
  { name: 'BROOKLIN', lat: -23.61, lng: -46.69 },
  { name: 'PERDIZES / POMPEIA', lat: -23.532, lng: -46.682 },
  { name: 'LIBERDADE', lat: -23.559, lng: -46.635 },
  { name: 'SANTA CECÍLIA', lat: -23.5405, lng: -46.6535 },
  { name: 'BOM RETIRO', lat: -23.527, lng: -46.643 },
  { name: 'MOOCA', lat: -23.5555, lng: -46.5985 },
  { name: 'IPIRANGA', lat: -23.592, lng: -46.61 },
]

export const CLASSIFY_MAX_KM = 2

export function distanceKm(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const R = 6371
  const rad = (x: number) => (x * Math.PI) / 180
  const dLat = rad(bLat - aLat)
  const dLng = rad(bLng - aLng)
  const h = Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(aLat)) * Math.cos(rad(bLat)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

export function classify(lat: number, lng: number): string | null {
  let best: string | null = null
  let bestD = Infinity
  for (const b of BAIRROS) {
    const d = distanceKm(lat, lng, b.lat, b.lng)
    if (d < bestD) { bestD = d; best = b.name }
  }
  return bestD <= CLASSIFY_MAX_KM ? best : null
}
