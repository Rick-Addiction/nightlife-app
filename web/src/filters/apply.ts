import type { EventWithGeo } from '../data/join'
import type { FilterState } from './state'
import { classify, distanceKm } from '../data/bairros'
import { igActivity } from '../data/vivacity'

export const NEAR_ME_KM = 3

export function applyClientFilters(
  events: EventWithGeo[], f: FilterState, now: Date = new Date(),
): EventWithGeo[] {
  return events.filter((e) => {
    if (f.genres.length > 0 && (!e.genre || !f.genres.includes(e.genre))) return false
    if (f.bairro && (!e.mappable || classify(e.lat!, e.lng!) !== f.bairro)) return false
    if (f.nearMe &&
        (!e.mappable || distanceKm(f.nearMe.lat, f.nearMe.lng, e.lat!, e.lng!) > NEAR_ME_KM)) return false
    if (f.extras.ticket && !e.ticket_url) return false
    if (f.extras.flyer && !e.flyer_url) return false
    if (f.extras.igAtivo && igActivity(e.venueIgLastPostAt, now) === null) return false
    return true
  })
}
