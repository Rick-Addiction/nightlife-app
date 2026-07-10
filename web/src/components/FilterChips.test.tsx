import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterChips } from './FilterChips'
import { initialFilters } from '../filters/state'

describe('FilterChips', () => {
  it('marca o preset ativo e dispara setPreset ao clicar', async () => {
    const dispatch = vi.fn()
    render(<FilterChips filters={{ ...initialFilters, preset: 'today' }} dispatch={dispatch} />)
    expect(screen.getByRole('button', { name: 'HOJE' })).toHaveClass('on')
    await userEvent.click(screen.getByRole('button', { name: 'FDS' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'setPreset', preset: 'weekend' })
  })

  it('renderiza os 5 presets', () => {
    render(<FilterChips filters={initialFilters} dispatch={() => {}} />)
    for (const label of ['PRÓXIMAS', 'HOJE', 'AMANHÃ', 'FDS', 'TUDO']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
  })
})
