export interface VenueOut {
  id: number
  name: string
  category: string | null
  lat: number | null
  lng: number | null
  address: string | null
  status: string
  confidence: number
  effective_confidence: number
  is_monitored: boolean
}

export interface EventOut {
  id: number
  name: string
  starts_at: string | null
  ends_at: string | null
  venue_id: number | null
  status: string
  genre: string | null
  ticket_url: string | null
  confidence: number
  effective_confidence: number
}
