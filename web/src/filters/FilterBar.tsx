import type { Dispatch } from 'react'
import type { FilterAction, FilterState, Preset } from './state'

export type View = 'list' | 'split'

const PRESETS: { key: Preset; label: string }[] = [
  { key: 'upcoming', label: 'Próximos' },
  { key: 'today', label: 'Hoje' },
  { key: 'weekend', label: 'Fim de semana' },
  { key: 'all', label: 'Tudo' },
]

export function FilterBar({ filters, genres, dispatch, view, onView }: {
  filters: FilterState
  genres: string[]
  dispatch: Dispatch<FilterAction>
  view: View
  onView: (v: View) => void
}) {
  return (
    <div className="filterbar" style={{ display: 'flex', gap: 12, alignItems: 'center', padding: 12, borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
      <strong style={{ color: 'var(--cyan)', letterSpacing: 1 }}>RADAR SP</strong>

      <select value={filters.preset} onChange={(e) => dispatch({ type: 'setPreset', preset: e.target.value as Preset })}>
        {PRESETS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
      </select>

      <label>Gênero
        <select aria-label="gênero" value={filters.genre ?? ''}
                onChange={(e) => dispatch({ type: 'setGenre', genre: e.target.value || null })}>
          <option value="">todos</option>
          {genres.map((g) => <option key={g} value={g}>{g}</option>)}
        </select>
      </label>

      <label>Confiança ≥ {filters.minConfidence}
        <input type="range" min={0} max={100} step={10} value={filters.minConfidence}
               onChange={(e) => dispatch({ type: 'setMinConfidence', value: Number(e.target.value) })} />
      </label>

      <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
        <button onClick={() => onView('list')} aria-pressed={view === 'list'}
                style={{ fontWeight: view === 'list' ? 700 : 400 }}>Só lista</button>
        <button onClick={() => onView('split')} aria-pressed={view === 'split'}
                style={{ fontWeight: view === 'split' ? 700 : 400 }}>Lista + Mapa</button>
      </div>
    </div>
  )
}
