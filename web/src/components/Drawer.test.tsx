import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Drawer } from './Drawer'

describe('Drawer', () => {
  it('renderiza label e children; tap no handle alterna closed->half', async () => {
    const onState = vi.fn()
    render(
      <Drawer state="closed" onState={onState} label="12 FESTAS">
        <div>conteudo da lista</div>
      </Drawer>,
    )
    expect(screen.getByText('12 FESTAS')).toBeInTheDocument()
    expect(screen.getByText('conteudo da lista')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /12 FESTAS/ }))
    expect(onState).toHaveBeenCalledWith('half')
  })
  it('tap com gaveta aberta fecha', async () => {
    const onState = vi.fn()
    render(<Drawer state="half" onState={onState} label="X"><div /></Drawer>)
    await userEvent.click(screen.getByRole('button', { name: /X/ }))
    expect(onState).toHaveBeenCalledWith('closed')
  })
})
