import type { SweepAcoes, SweepOut } from '../api/sweep'

export function acoesLabel(acoes?: SweepAcoes): string {
  if (!acoes) return '—'
  const ignoreTotal = acoes.ignore
    ? Object.values(acoes.ignore).reduce((a, b) => a + b, 0) : 0
  return `+${acoes.add ?? 0} · ✕${acoes.cancel ?? 0} · ign ${ignoreTotal}`
}

export function SweepReport({ sweep, onClose }: { sweep: SweepOut; onClose: () => void }) {
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 45, background: 'rgba(0,0,0,0.75)' }}
         onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           style={{ position: 'absolute', left: 0, right: 0, bottom: 0, maxHeight: '88dvh',
                    overflowY: 'auto', background: 'var(--black)',
                    borderTop: '3px solid var(--green)', padding: '10px 12px 20px' }}>
        <div className="hline" style={{ fontSize: 20 }}>RELATÓRIO DA VARREDURA
          {sweep.label ? ` — ${sweep.label.toUpperCase()}` : ''}</div>
        <div className="label" style={{ margin: '4px 0 10px' }}>
          {sweep.done_handles}/{sweep.total_handles} PERFIS · STATUS {sweep.status.toUpperCase()}
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead>
              <tr className="label" style={{ textAlign: 'left' }}>
                <th style={{ padding: 4 }}>LOCAL</th><th>HANDLE</th><th>STATUS</th>
                <th>POSTS</th><th>FLYERS</th><th>FESTAS CRIADAS</th><th>AÇÕES</th>
              </tr>
            </thead>
            <tbody>
              {sweep.report.map((i) => (
                <tr key={i.handle} style={{ borderTop: '1px solid var(--line)', verticalAlign: 'top' }}>
                  <td style={{ padding: 4, fontWeight: 800 }}>{i.venue_name ?? '—'}</td>
                  <td style={{ padding: 4, color: 'var(--muted)' }}>@{i.handle}</td>
                  <td style={{ padding: 4 }}>
                    {i.status === 'ok'
                      ? <span style={{ color: 'var(--green)', fontWeight: 800 }}>OK</span>
                      : <span style={{ color: 'var(--pink)', fontWeight: 800 }} title={i.erro}>FALHA</span>}
                  </td>
                  <td style={{ padding: 4 }}>{i.posts_novos}</td>
                  <td style={{ padding: 4 }}>{i.flyers.length}</td>
                  <td style={{ padding: 4 }}>
                    {i.festas.length === 0 && <span style={{ color: 'var(--dim)' }}>—</span>}
                    {i.festas.map((f) => (
                      <div key={f.event_id}>
                        <span>{f.anchored ? '✓' : '⚠'}</span> {f.name}
                        {f.starts_at && <span style={{ color: 'var(--muted)' }}>
                          {' '}({f.starts_at.slice(0, 10)})</span>}
                      </div>
                    ))}
                  </td>
                  <td style={{ padding: 4, color: 'var(--muted)' }}>{acoesLabel(i.acoes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
