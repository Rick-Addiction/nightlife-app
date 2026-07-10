import type { EventQuery } from '../api/client'

export type Preset = 'upcoming' | 'today' | 'tomorrow' | 'weekend' | 'all'

export interface FilterState {
  preset: Preset
  genre: string | null
  minConfidence: number
  includePast: boolean
}

export const initialFilters: FilterState = {
  preset: 'upcoming', genre: null, minConfidence: 0, includePast: false,
}

export type FilterAction =
  | { type: 'setPreset'; preset: Preset }
  | { type: 'setGenre'; genre: string | null }
  | { type: 'setMinConfidence'; value: number }
  | { type: 'setIncludePast'; value: boolean }

export function filterReducer(state: FilterState, action: FilterAction): FilterState {
  switch (action.type) {
    case 'setPreset': return { ...state, preset: action.preset, includePast: action.preset === 'all' }
    case 'setGenre': return { ...state, genre: action.genre }
    case 'setMinConfidence': return { ...state, minConfidence: action.value }
    case 'setIncludePast': return { ...state, includePast: action.value }
  }
}

function isoDate(d: Date): string {
  // Dia do CALENDARIO LOCAL, nao UTC — app de vida noturna usado a noite:
  // toISOString() desloca +1 dia em fusos negativos (UTC-3) apos ~21h.
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function queryFromFilters(f: FilterState, now: Date = new Date()): EventQuery {
  const q: EventQuery = {}
  if (f.genre) q.genre = f.genre
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
  } else if (f.preset === 'all') {
    q.include_past = true
  }
  // 'upcoming' => sem datas (a API ja default-filtra futuro)
  return q
}
