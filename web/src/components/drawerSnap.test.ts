import { describe, it, expect } from 'vitest'
import { drawerHeight, snapTo, CLOSED_PX } from './drawerSnap'

describe('drawerSnap', () => {
  it('alturas dos 3 estados', () => {
    expect(drawerHeight('closed', 800)).toBe(CLOSED_PX)
    expect(drawerHeight('half', 800)).toBe(360)   // 45%
    expect(drawerHeight('full', 800)).toBe(680)   // 85%
  })
  it('snapTo escolhe o estado mais proximo', () => {
    expect(snapTo(70, 800)).toBe('closed')
    expect(snapTo(300, 800)).toBe('half')
    expect(snapTo(500, 800)).toBe('half')
    expect(snapTo(600, 800)).toBe('full')
    expect(snapTo(9999, 800)).toBe('full')
  })
})
