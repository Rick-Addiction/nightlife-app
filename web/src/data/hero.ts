import type { EventWithGeo } from './join'

/** Evento COM flyer vira o card-heroi do feed; entre eles prefere o que tem
 * data (sem-data e pior aposta de abertura) — sem-data so vira hero se nao
 * houver outro com flyer. O resto mantem a ordem. */
export function pickHero(events: EventWithGeo[]): { hero: EventWithGeo | null; rest: EventWithGeo[] } {
  const withFlyer = events.filter((e) => e.flyer_url)
  const chosen = withFlyer.find((e) => e.starts_at != null) ?? withFlyer[0]
  if (!chosen) return { hero: null, rest: events }
  const i = events.indexOf(chosen)
  return { hero: chosen, rest: [...events.slice(0, i), ...events.slice(i + 1)] }
}
