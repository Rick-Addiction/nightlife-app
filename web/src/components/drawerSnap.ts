export type DrawerState = 'closed' | 'half' | 'full'

export const CLOSED_PX = 64
const HALF = 0.45
const FULL = 0.85

export function drawerHeight(s: DrawerState, viewportH: number): number {
  if (s === 'closed') return CLOSED_PX
  return Math.round(viewportH * (s === 'half' ? HALF : FULL))
}

export function snapTo(px: number, viewportH: number): DrawerState {
  const states: DrawerState[] = ['closed', 'half', 'full']
  let best: DrawerState = 'closed'
  let bestD = Infinity
  for (const s of states) {
    const d = Math.abs(drawerHeight(s, viewportH) - px)
    if (d < bestD) { bestD = d; best = s }
  }
  return best
}
