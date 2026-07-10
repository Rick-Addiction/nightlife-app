import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterSheet } from './FilterSheet'
import { initialFilters } from '../filters/state'

const base = {
  filters: initialFilters, dispatch: () => {}, count: 12,
  genreOptions: ['funk', 'techno'], onClose: () => {},
}

describe('FilterSheet', () => {
  it('renderiza as secoes e o botao-resultado vivo', () => {
    render(<FilterSheet {...base} />)
    for (const sec of ['QUANDO', 'ONDE', 'SOM', 'EXTRAS', 'CONFIANÇA']) {
      expect(screen.getByText(sec)).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'VER 12 FESTAS →' })).toBeInTheDocument()
  })
  it('toggla genero e extra via dispatch', async () => {
    const dispatch = vi.fn()
    render(<FilterSheet {...base} dispatch={dispatch} />)
    await userEvent.click(screen.getByRole('button', { name: 'TECHNO' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'toggleGenre', genre: 'techno' })
    await userEvent.click(screen.getByRole('button', { name: 'COM FLYER' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'toggleExtra', key: 'flyer' })
  })
  it('seleciona bairro e confianca', async () => {
    const dispatch = vi.fn()
    render(<FilterSheet {...base} dispatch={dispatch} />)
    await userEvent.click(screen.getByRole('button', { name: 'AUGUSTA' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'setBairro', bairro: 'AUGUSTA' })
    await userEvent.click(screen.getByRole('button', { name: '70+' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'setMinConfidence', value: 70 })
  })
  it('PERTO DE MIM pede geolocation e dispara setNearMe', async () => {
    const dispatch = vi.fn()
    const getCurrentPosition = vi.fn((ok: PositionCallback) =>
      ok({ coords: { latitude: -23.55, longitude: -46.66 } } as GeolocationPosition))
    vi.stubGlobal('navigator', { ...navigator, geolocation: { getCurrentPosition } })
    render(<FilterSheet {...base} dispatch={dispatch} />)
    await userEvent.click(screen.getByRole('button', { name: /PERTO DE MIM/ }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'setNearMe', point: { lat: -23.55, lng: -46.66 } })
    vi.unstubAllGlobals()
  })
  it('VER fecha; LIMPAR dispara clearAll', async () => {
    const onClose = vi.fn()
    const dispatch = vi.fn()
    render(<FilterSheet {...base} onClose={onClose} dispatch={dispatch} />)
    await userEvent.click(screen.getByRole('button', { name: 'VER 12 FESTAS →' }))
    expect(onClose).toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'LIMPAR' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'clearAll' })
  })
})
