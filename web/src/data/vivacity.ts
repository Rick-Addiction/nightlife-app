// "Dia" = dia do calendario LOCAL do aparelho. Publico-alvo usa o app em SP
// (UTC-3), entao dia-local == dia-SP — espelha o _sp_day_start do backend
// sem arrastar biblioteca de timezone pro bundle.
import type { EventWithGeo } from './join'

export const IG_ACTIVE_DAYS = 30
export type IgActivity = 'hoje' | 'ativo' | null

function sameLocalDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
}

export function igActivity(iso: string | null, now: Date = new Date()): IgActivity {
  if (!iso) return null
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  if (sameLocalDay(d, now)) return 'hoje'
  const days = (now.getTime() - d.getTime()) / 86_400_000
  return days <= IG_ACTIVE_DAYS ? 'ativo' : null
}

export function venueIdsWithEventToday(events: EventWithGeo[], now: Date = new Date()): Set<number> {
  const out = new Set<number>()
  for (const e of events) {
    if (e.venue_id == null || !e.starts_at) continue
    const d = new Date(e.starts_at)
    if (!isNaN(d.getTime()) && sameLocalDay(d, now)) out.add(e.venue_id)
  }
  return out
}
