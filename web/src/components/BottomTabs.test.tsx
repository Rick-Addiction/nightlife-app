import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BottomTabs } from './BottomTabs'

describe('BottomTabs', () => {
  it('marca a aba ativa e troca ao clicar', async () => {
    const onTab = vi.fn()
    render(<BottomTabs tab="festas" onTab={onTab} />)
    expect(screen.getByRole('button', { name: 'FESTAS' })).toHaveClass('on')
    await userEvent.click(screen.getByRole('button', { name: 'MAPA' }))
    expect(onTab).toHaveBeenCalledWith('mapa')
  })
})
