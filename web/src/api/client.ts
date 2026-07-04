import type { EventOut, VenueOut } from './types'

export type EventQuery = {
  date_from?: string
  date_to?: string
  genre?: string
  min_confidence?: number
  bbox?: string
  include_past?: boolean
}

export type VenueQuery = {
  type?: string
  min_confidence?: number
  bbox?: string
}

export function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const parts: string[] = []
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '' || value === null) continue
    parts.push(`${key}=${encodeURIComponent(String(value))}`)
  }
  return parts.length ? `?${parts.join('&')}` : ''
}

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`API ${resp.status} em ${url}`)
  return resp.json() as Promise<T>
}

export function fetchEvents(q: EventQuery): Promise<EventOut[]> {
  return getJson<EventOut[]>(`/api/events${buildQuery(q)}`)
}

export function fetchVenues(q: VenueQuery = {}): Promise<VenueOut[]> {
  return getJson<VenueOut[]>(`/api/venues${buildQuery(q)}`)
}
