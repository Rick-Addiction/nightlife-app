import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
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
  it('drag para cima solta no snap mais proximo (half)', () => {
    const onState = vi.fn()
    render(<Drawer state="closed" onState={onState} label="X"><div /></Drawer>)
    const handle = screen.getByRole('button', { name: /X/ })
    fireEvent.pointerDown(handle, { clientY: 700, pointerId: 1 })
    fireEvent.pointerMove(handle, { clientY: 400, pointerId: 1 })   // sobe ~300px
    fireEvent.pointerUp(handle, { clientY: 400, pointerId: 1 })
    expect(onState).toHaveBeenCalledWith('half')
  })
  it('pointercancel no meio do drag reseta sem mudar estado', () => {
    const onState = vi.fn()
    render(<Drawer state="closed" onState={onState} label="X"><div /></Drawer>)
    const handle = screen.getByRole('button', { name: /X/ })
    fireEvent.pointerDown(handle, { clientY: 700, pointerId: 1 })
    fireEvent.pointerMove(handle, { clientY: 400, pointerId: 1 })
    fireEvent.pointerCancel(handle, { pointerId: 1 })
    expect(onState).not.toHaveBeenCalled()
    // proximo tap ainda funciona (start.current foi limpo)
    fireEvent.pointerDown(handle, { clientY: 700, pointerId: 2 })
    fireEvent.pointerUp(handle, { clientY: 700, pointerId: 2 })
    expect(onState).toHaveBeenCalledWith('half')
  })
})
