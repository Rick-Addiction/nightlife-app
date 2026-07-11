import type { SweepOut } from '../api/sweep'

export type SweepMode = 'idle' | 'picking' | { lat: number; lng: number; km: number }

// painel flutuante do fluxo de varredura: confirmacao (circulo escolhido),
// progresso (poll) e diff final com acesso ao relatorio
export function SweepPanel({ mode, count, sweep, onConfirm, onCancel, onKm, onOpenReport, posting }: {
  mode: SweepMode; count: number; sweep: SweepOut | null
  onConfirm: () => void; onCancel: () => void
  onKm: (km: number) => void; onOpenReport: () => void
  posting?: boolean
}) {
  const wrap: React.CSSProperties = {
    position: 'absolute', left: 10, right: 10, bottom: 76, zIndex: 15,
    background: 'var(--black)', border: '2px solid var(--pink)', padding: 10,
  }
  if (typeof mode === 'object') {
    return (
      <div style={wrap}>
        <div className="label">RAIO: {mode.km.toFixed(1)} KM</div>
        <input type="range" min={0.5} max={5} step={0.5} value={mode.km}
               aria-label="RAIO" onChange={(e) => onKm(Number(e.target.value))}
               style={{ width: '100%', accentColor: 'var(--pink)' }} />
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button className="b-btn" style={{ width: 100 }} onClick={onCancel}>CANCELAR</button>
          <button className="b-btn primary" style={{ flex: 1 }} onClick={onConfirm} disabled={posting}>
            {`VARRER ${count} PERFIS →`}
          </button>
        </div>
      </div>
    )
  }
  if (sweep?.status === 'running') {
    const txt = sweep.phase === 'extraindo'
      ? 'EXTRAINDO FLYERS…'
      : `VARRENDO ${sweep.done_handles}/${sweep.total_handles}`
    return (
      <div style={{ ...wrap, display: 'flex', alignItems: 'center', gap: 10 }}>
        <span className="label" style={{ color: 'var(--green)' }}>⌖ {txt}</span>
        <button className="chip" style={{ marginLeft: 'auto' }} onClick={onOpenReport}>PARCIAL</button>
      </div>
    )
  }
  // W3: erro tem prioridade sobre o diff — mesmo que diff exista (extracao
  // falhou depois de casar alguns flyers), o usuario precisa ver que quebrou.
  if (sweep?.status === 'error') {
    return (
      <div style={{ ...wrap, display: 'flex', alignItems: 'center', gap: 10 }}>
        <span className="label" style={{ color: 'var(--pink)' }}>{sweep.error || 'FALHOU'}</span>
        <button className="chip grn" style={{ marginLeft: 'auto' }} onClick={onOpenReport}>RELATÓRIO</button>
        <button className="chip" onClick={onCancel}>✕</button>
      </div>
    )
  }
  if (sweep?.status === 'done' && sweep.diff) {
    return (
      <div style={{ ...wrap, display: 'flex', alignItems: 'center', gap: 10 }}>
        <span className="label" style={{ color: 'var(--green)' }}>
          +{sweep.diff.novas_festas} FESTAS · +{sweep.diff.venues_com_pin_novo.length} LOCAIS COM PIN
        </span>
        <button className="chip grn" style={{ marginLeft: 'auto' }} onClick={onOpenReport}>RELATÓRIO</button>
        <button className="chip" onClick={onCancel}>✕</button>
      </div>
    )
  }
  return null
}
