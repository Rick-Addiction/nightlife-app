import type { EventWithGeo } from './join'

/** Primeiro evento COM flyer vira o card-heroi do feed; o resto mantem a ordem. */
export function pickHero(events: EventWithGeo[]): { hero: EventWithGeo | null; rest: EventWithGeo[] } {
  const i = events.findIndex((e) => e.flyer_url)
  if (i === -1) return { hero: null, rest: events }
  return { hero: events[i], rest: [...events.slice(0, i), ...events.slice(i + 1)] }
}
