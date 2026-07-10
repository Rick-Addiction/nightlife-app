import type { Dispatch } from 'react'
import type { FilterAction, FilterState, Preset } from '../filters/state'

const PRESETS: { key: Preset; label: string }[] = [
  { key: 'upcoming', label: 'PRÓXIMAS' },
  { key: 'today', label: 'HOJE' },
  { key: 'tomorrow', label: 'AMANHÃ' },
  { key: 'weekend', label: 'FDS' },
  { key: 'all', label: 'TUDO' },
]

export function FilterChips({ filters, dispatch, activeCount, onOpenSheet }: {
  filters: FilterState; dispatch: Dispatch<FilterAction>
  activeCount: number; onOpenSheet: () => void
}) {
  return (
    <div style={{ display: 'flex', gap: 5, padding: '6px 12px', overflowX: 'auto' }}>
      {PRESETS.map((p) => (
        <button key={p.key} className={`chip${filters.preset === p.key ? ' on' : ''}`}
                onClick={() => dispatch({ type: 'setPreset', preset: p.key })}>
          {p.label}
        </button>
      ))}
      <button className={`chip${activeCount > 0 ? ' grn' : ''}`} onClick={onOpenSheet}>
        {`≡ FILTROS${activeCount > 0 ? ` ·${activeCount}` : ''}`}
      </button>
    </div>
  )
}
