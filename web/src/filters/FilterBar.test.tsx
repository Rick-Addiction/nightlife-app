import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterBar } from './FilterBar'
import { initialFilters } from './state'

describe('FilterBar', () => {
  it('dispara setGenre ao escolher genero', async () => {
    const dispatch = vi.fn()
    render(<FilterBar filters={initialFilters} genres={['techno', 'house']} dispatch={dispatch}
                     view="split" onView={() => {}} />)
    await userEvent.selectOptions(screen.getByLabelText(/gênero/i), 'techno')
    expect(dispatch).toHaveBeenCalledWith({ type: 'setGenre', genre: 'techno' })
  })
  it('dispara troca de visao', async () => {
    const onView = vi.fn()
    render(<FilterBar filters={initialFilters} genres={[]} dispatch={() => {}}
                     view="split" onView={onView} />)
    await userEvent.click(screen.getByRole('button', { name: /só lista/i }))
    expect(onView).toHaveBeenCalledWith('list')
  })
})
