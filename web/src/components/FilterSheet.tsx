import { useState } from 'react'
import type { Dispatch } from 'react'
import type { FilterAction, FilterState, Extras } from '../filters/state'
import { BAIRROS } from '../data/bairros'

const EXTRAS: { key: keyof Extras; label: string }[] = [
  { key: 'ticket', label: 'COM TICKET' },
  { key: 'flyer', label: 'COM FLYER' },
  { key: 'igAtivo', label: 'IG ATIVO' },
]
const CONFS = [{ v: 0, label: 'TODAS' }, { v: 40, label: '40+' }, { v: 70, label: '70+' }]

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ padding: '10px 12px 2px' }}>
      <div className="label" style={{ marginBottom: 7 }}>{title}</div>
      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>{children}</div>
    </div>
  )
}

export function FilterSheet({ filters, dispatch, count, genreOptions, onClose }: {
  filters: FilterState; dispatch: Dispatch<FilterAction>
  count: number; genreOptions: string[]; onClose: () => void
}) {
  const [gpsDenied, setGpsDenied] = useState(false)
  // uniao: genero selecionado continua visivel (e des-togglavel) mesmo se o
  // fetch atual nao tiver nenhum evento dele
  const genres = [...new Set([...genreOptions, ...filters.genres])].sort()

  const nearMeClick = () => {
    if (filters.nearMe) { dispatch({ type: 'setNearMe', point: null }); return }
    navigator.geolocation?.getCurrentPosition(
      (pos) => dispatch({ type: 'setNearMe',
                          point: { lat: pos.coords.latitude, lng: pos.coords.longitude } }),
      () => setGpsDenied(true),  // negado: chip apaga, resto intacto (spec §7)
    )
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 40, background: 'rgba(0,0,0,0.65)' }}
         onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           style={{ position: 'absolute', left: 0, right: 0, bottom: 0, maxHeight: '88dvh',
                    display: 'flex', flexDirection: 'column', background: 'var(--black)',
                    borderTop: '3px solid var(--pink)', animation: 'b-slide-up 0.18s ease-out' }}>
        <div style={{ overflowY: 'auto', paddingBottom: 8 }}>
          <Section title="QUANDO">
            {([['upcoming', 'PRÓXIMAS'], ['today', 'HOJE'], ['tomorrow', 'AMANHÃ'],
               ['weekend', 'FDS'], ['all', 'TUDO']] as const).map(([key, label]) => (
              <button key={key} className={`chip${filters.preset === key ? ' on' : ''}`}
                      onClick={() => dispatch({ type: 'setPreset', preset: key })}>{label}</button>
            ))}
            <input type="date" value={filters.date ?? ''} aria-label="DATA"
                   // limpar o input nao tem acao propria: sair do preset 'date' e via chips
                   onChange={(e) => e.target.value && dispatch({ type: 'setDate', date: e.target.value })}
                   className={`chip${filters.preset === 'date' ? ' on' : ''}`}
                   style={{ colorScheme: 'dark' }} />
          </Section>
          <Section title="ONDE">
            <button className={`chip grn${filters.nearMe ? ' on' : ''}`}
                    disabled={gpsDenied} style={gpsDenied ? { opacity: 0.35 } : undefined}
                    onClick={nearMeClick}>⌖ PERTO DE MIM</button>
            {BAIRROS.map((b) => (
              <button key={b.name} className={`chip${filters.bairro === b.name ? ' on' : ''}`}
                      onClick={() => dispatch({ type: 'setBairro',
                                                bairro: filters.bairro === b.name ? null : b.name })}>
                {b.name}
              </button>
            ))}
          </Section>
          <Section title="SOM">
            {genres.length === 0 && (
              <span className="label" style={{ fontWeight: 700 }}>SEM GÊNEROS NOS RESULTADOS</span>
            )}
            {genres.map((g) => (
              <button key={g} className={`chip${filters.genres.includes(g) ? ' on' : ''}`}
                      onClick={() => dispatch({ type: 'toggleGenre', genre: g })}>
                {g.toUpperCase()}
              </button>
            ))}
          </Section>
          <Section title="EXTRAS">
            {EXTRAS.map((x) => (
              <button key={x.key} className={`chip${filters.extras[x.key] ? ' on' : ''}`}
                      onClick={() => dispatch({ type: 'toggleExtra', key: x.key })}>{x.label}</button>
            ))}
          </Section>
          <Section title="CONFIANÇA">
            {CONFS.map((c) => (
              <button key={c.v} className={`chip${filters.minConfidence === c.v ? ' on' : ''}`}
                      onClick={() => dispatch({ type: 'setMinConfidence', value: c.v })}>{c.label}</button>
            ))}
          </Section>
        </div>
        <div style={{ display: 'flex', gap: 8, padding: 10, borderTop: '1px solid var(--line)' }}>
          <button className="b-btn" style={{ width: 110 }}
                  onClick={() => dispatch({ type: 'clearAll' })}>LIMPAR</button>
          <button className="b-btn primary" style={{ flex: 1 }}
                  onClick={onClose}>{`VER ${count} FESTAS →`}</button>
        </div>
      </div>
    </div>
  )
}
