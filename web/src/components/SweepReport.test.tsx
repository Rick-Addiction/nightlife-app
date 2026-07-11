import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SweepReport } from './SweepReport'
import type { SweepOut } from '../api/sweep'

const sweep: SweepOut = {
  id: 1, label: 'augusta', status: 'done', phase: 'done', total_handles: 2, done_handles: 2,
  report: [
    { venue_id: 1, venue_name: 'Aura Club', handle: 'aura.clubsp', status: 'ok',
      posts_novos: 3, flyers: ['SC1', 'SC2'],
      festas: [{ event_id: 9, name: 'Expand Your Aura', starts_at: '2026-07-11T02:00:00Z', anchored: true }] },
    { venue_id: 2, venue_name: 'Quebrado Bar', handle: 'quebrado', status: 'falha',
      posts_novos: 0, flyers: [], festas: [], erro: 'timeout' },
  ],
  diff: null, error: null, started_at: '2026-07-10T20:00:00Z', finished_at: null,
}

describe('SweepReport', () => {
  it('linha por local com handle, contagens, festas e marcador de ancora', () => {
    render(<SweepReport sweep={sweep} onClose={() => {}} />)
    expect(screen.getByText('Aura Club')).toBeInTheDocument()
    expect(screen.getByText('@aura.clubsp')).toBeInTheDocument()
    expect(screen.getByText('Expand Your Aura')).toBeInTheDocument()
    expect(screen.getByText('✓')).toBeInTheDocument()      // ancorada
    expect(screen.getByText('FALHA')).toBeInTheDocument()  // status do quebrado
  })
})
