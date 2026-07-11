import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SweepPanel } from './SweepPanel'
import type { SweepOut } from '../api/sweep'

const runningSweep: SweepOut = {
  id: 1, label: null, status: 'running', phase: 'varrendo', total_handles: 66,
  done_handles: 12, report: [], diff: null, error: null,
  started_at: '2026-07-10T20:00:00Z', finished_at: null,
}
const doneSweep: SweepOut = {
  ...runningSweep, status: 'done', phase: 'done', done_handles: 66,
  diff: { novas_festas: 9, venues_com_pin_novo: ['Aura', 'Selva Club'] }, finished_at: '2026-07-10T21:00:00Z',
}
const erroredSweep: SweepOut = {
  ...runningSweep, status: 'error', error: 'processo morto', diff: null,
  finished_at: '2026-07-10T20:05:00Z',
}

describe('SweepPanel', () => {
  it('confirmacao mostra contagem e dispara onConfirm com o raio do slider', async () => {
    const onConfirm = vi.fn()
    render(<SweepPanel mode={{ lat: -23.553, lng: -46.656, km: 2 }} count={41}
                       sweep={null} onConfirm={onConfirm} onCancel={() => {}}
                       onKm={() => {}} onOpenReport={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'VARRER 41 PERFIS →' }))
    expect(onConfirm).toHaveBeenCalled()
  })
  it('fase varrendo mostra progresso', () => {
    render(<SweepPanel mode="idle" count={0} sweep={runningSweep}
                       onConfirm={() => {}} onCancel={() => {}} onKm={() => {}} onOpenReport={() => {}} />)
    expect(screen.getByText(/VARRENDO 12\/66/)).toBeInTheDocument()
  })
  it('done mostra o diff e abre o relatorio', async () => {
    const onOpenReport = vi.fn()
    render(<SweepPanel mode="idle" count={0} sweep={doneSweep}
                       onConfirm={() => {}} onCancel={() => {}} onKm={() => {}} onOpenReport={onOpenReport} />)
    expect(screen.getByText(/\+9 FESTAS/)).toBeInTheDocument()
    expect(screen.getByText(/\+2 LOCAIS COM PIN/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'RELATÓRIO' }))
    expect(onOpenReport).toHaveBeenCalled()
  })
  it('erro mostra a mensagem em destaque e ainda da acesso ao relatorio (W3)', () => {
    render(<SweepPanel mode="idle" count={0} sweep={erroredSweep}
                       onConfirm={() => {}} onCancel={() => {}} onKm={() => {}} onOpenReport={() => {}} />)
    expect(screen.getByText(/FALHOU|processo morto/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'RELATÓRIO' })).toBeInTheDocument()
  })
})
