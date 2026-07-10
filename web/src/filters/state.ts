import type { EventQuery } from '../api/client'

export type Preset = 'upcoming' | 'today' | 'tomorrow' | 'weekend' | 'date' | 'all'

export interface Extras { ticket: boolean; flyer: boolean; igAtivo: boolean }

export interface FilterState {
  preset: Preset
  date: string | null                       // YYYY-MM-DD quando preset='date'
  genres: string[]                          // multi, client-side
  minConfidence: number
  includePast: boolean
  bairro: string | null                     // exclusivo com nearMe
  nearMe: { lat: number; lng: number } | null
  extras: Extras
}

export const initialFilters: FilterState = {
  preset: 'upcoming', date: null, genres: [], minConfidence: 0, includePast: false,
  bairro: null, nearMe: null, extras: { ticket: false, flyer: false, igAtivo: false },
}

export type FilterAction =
  | { type: 'setPreset'; preset: Preset }
  | { type: 'setDate'; date: string }
  | { type: 'toggleGenre'; genre: string }
  | { type: 'setMinConfidence'; value: number }
  | { type: 'setIncludePast'; value: boolean }
  | { type: 'setBairro'; bairro: string | null }
  | { type: 'setNearMe'; point: { lat: number; lng: number } | null }
  | { type: 'toggleExtra'; key: keyof Extras }
  | { type: 'clearAll' }

export function filterReducer(state: FilterState, action: FilterAction): FilterState {
  switch (action.type) {
    case 'setPreset':
      return { ...state, preset: action.preset, date: null, includePast: action.preset === 'all' }
    case 'setDate':
      return { ...state, preset: 'date', date: action.date, includePast: false }
    case 'toggleGenre':
      return {
        ...state,
        genres: state.genres.includes(action.genre)
          ? state.genres.filter((g) => g !== action.genre)
          : [...state.genres, action.genre],
      }
    case 'setMinConfidence': return { ...state, minConfidence: action.value }
    case 'setIncludePast': return { ...state, includePast: action.value }
    case 'setBairro':
      return { ...state, bairro: action.bairro, nearMe: action.bairro ? null : state.nearMe }
    case 'setNearMe':
      return { ...state, nearMe: action.point, bairro: action.point ? null : state.bairro }
    case 'toggleExtra':
      return { ...state, extras: { ...state.extras, [action.key]: !state.extras[action.key] } }
    case 'clearAll': return initialFilters
  }
}

export function activeFilterCount(f: FilterState): number {
  let n = 0
  if (f.genres.length > 0) n++
  if (f.bairro) n++
  if (f.nearMe) n++
  if (f.extras.ticket) n++
  if (f.extras.flyer) n++
  if (f.extras.igAtivo) n++
  if (f.minConfidence > 0) n++
  return n
}

function isoDate(d: Date): string {
  // Dia do CALENDARIO LOCAL, nao UTC — app de vida noturna usado a noite:
  // toISOString() desloca +1 dia em fusos negativos (UTC-3) apos ~21h.
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function queryFromFilters(f: FilterState, now: Date = new Date()): EventQuery {
  const q: EventQuery = {}
  if (f.minConfidence > 0) q.min_confidence = f.minConfidence

  if (f.preset === 'today') {
    q.date_from = isoDate(now)
    q.date_to = isoDate(now)
  } else if (f.preset === 'tomorrow') {
    const t = new Date(now); t.setDate(now.getDate() + 1)
    q.date_from = isoDate(t)
    q.date_to = isoDate(t)
  } else if (f.preset === 'weekend') {
    // proxima sexta ate domingo
    const day = now.getDay() // 0=dom..6=sab
    const toFri = (5 - day + 7) % 7
    const fri = new Date(now); fri.setDate(now.getDate() + toFri)
    const sun = new Date(fri); sun.setDate(fri.getDate() + 2)
    q.date_from = isoDate(fri)
    q.date_to = isoDate(sun)
  } else if (f.preset === 'date' && f.date) {
    q.date_from = f.date
    q.date_to = f.date
  } else if (f.preset === 'all') {
    q.include_past = true
  }
  // 'upcoming' => sem datas (a API ja default-filtra futuro)
  return q
}
