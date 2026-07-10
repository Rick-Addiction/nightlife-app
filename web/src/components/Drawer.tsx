import { useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { CLOSED_PX, drawerHeight, snapTo, type DrawerState } from './drawerSnap'

const HANDLE_PX = 36

// Gaveta 3 estados (spec §7): discretos, transform/transition, SEM fisica.
// Drag so no handle (touch-action none) — o conteudo rola normal.
export function Drawer({ state, onState, bottom = 44, label, children }: {
  state: DrawerState; onState: (s: DrawerState) => void
  bottom?: number; label: string; children: ReactNode
}) {
  const [dragPx, setDragPx] = useState<number | null>(null)
  const start = useRef<{ y: number; h: number; moved: boolean } | null>(null)
  const vh = () => window.innerHeight - bottom
  const h = dragPx ?? drawerHeight(state, vh())

  const onPointerDown = (e: React.PointerEvent) => {
    ;(e.target as Element).setPointerCapture?.(e.pointerId)
    start.current = { y: e.clientY, h, moved: false }
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (!start.current) return
    const next = start.current.h + (start.current.y - e.clientY)
    if (Math.abs(e.clientY - start.current.y) > 5) start.current.moved = true
    setDragPx(Math.min(Math.max(next, CLOSED_PX), Math.round(vh() * 0.9)))
  }
  const onPointerUp = () => {
    if (!start.current) return
    if (start.current.moved && dragPx != null) onState(snapTo(dragPx, vh()))
    else onState(state === 'closed' ? 'half' : 'closed')  // tap alterna
    start.current = null
    setDragPx(null)
  }

  return (
    <div style={{ position: 'fixed', left: 0, right: 0, bottom, height: h, zIndex: 20,
                  background: 'var(--black)', borderTop: '3px solid var(--pink)',
                  transition: dragPx == null ? 'height 0.18s ease-out' : 'none',
                  display: 'flex', flexDirection: 'column' }}>
      <button aria-label={label}
              onPointerDown={onPointerDown} onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              style={{ height: HANDLE_PX, flex: 'none', touchAction: 'none',
                       background: 'none', border: 'none', cursor: 'grab',
                       display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
        <span style={{ width: 44, height: 4, background: 'var(--pink)' }} />
        <span className="label" style={{ color: 'var(--text)' }}>{label}</span>
      </button>
      <div style={{ overflowY: 'auto', flex: 1,
                    visibility: state === 'closed' && dragPx == null ? 'hidden' : 'visible' }}>
        {children}
      </div>
    </div>
  )
}
