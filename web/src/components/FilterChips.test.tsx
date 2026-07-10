import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterChips } from './FilterChips'
import { initialFilters } from '../filters/state'

describe('FilterChips', () => {
  it('marca o preset ativo e dispara setPreset ao clicar', async () => {
    const dispatch = vi.fn()
    render(<FilterChips filters={{ ...initialFilters, preset: 'today' }} dispatch={dispatch}
                        activeCount={0} onOpenSheet={() => {}} />)
    expect(screen.getByRole('button', { name: 'HOJE' })).toHaveClass('on')
    await userEvent.click(screen.getByRole('button', { name: 'FDS' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'setPreset', preset: 'weekend' })
  })

  it('renderiza os 5 presets', () => {
    render(<FilterChips filters={initialFilters} dispatch={() => {}}
                        activeCount={0} onOpenSheet={() => {}} />)
    for (const label of ['PRÓXIMAS', 'HOJE', 'AMANHÃ', 'FDS', 'TUDO']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
  })

  it('botao FILTROS abre o sheet e mostra contador quando ha filtro ativo', async () => {
    const onOpenSheet = vi.fn()
    render(<FilterChips filters={initialFilters} dispatch={() => {}}
                        activeCount={2} onOpenSheet={onOpenSheet} />)
    const btn = screen.getByRole('button', { name: /FILTROS/ })
    expect(btn).toHaveTextContent('≡ FILTROS ·2')
    await userEvent.click(btn)
    expect(onOpenSheet).toHaveBeenCalled()
  })
  it('sem filtro ativo o botao nao tem contador', () => {
    render(<FilterChips filters={initialFilters} dispatch={() => {}}
                        activeCount={0} onOpenSheet={() => {}} />)
    expect(screen.getByRole('button', { name: /FILTROS/ })).toHaveTextContent('≡ FILTROS')
    expect(screen.queryByText(/·/)).toBeNull()
  })
})
