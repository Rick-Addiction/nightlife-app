import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EventCard } from './EventCard'
import type { EventWithGeo } from '../data/join'

const ev = (over: Partial<EventWithGeo>): EventWithGeo => ({
  id: 1, name: 'Mamba Negra', starts_at: '2099-07-12T23:00:00-03:00', ends_at: null,
  venue_id: 5, status: 'scheduled', genre: 'Techno', ticket_url: null, confidence: 85,
  effective_confidence: 85, flyer_url: null, venueName: 'Selva Club',
  lat: -23.55, lng: -46.65, mappable: true, ...over,
})

describe('EventCard', () => {
  it('hero mostra o flyer grande e o nome', () => {
    render(<EventCard event={ev({ flyer_url: '/flyers/ABC.jpg' })} variant="hero" onOpen={() => {}} />)
    const img = screen.getByRole('img')
    expect(img).toHaveAttribute('src', '/flyers/ABC.jpg')
    expect(screen.getByText('Mamba Negra')).toBeInTheDocument()
    expect(screen.getByText('85')).toBeInTheDocument()
  })

  it('linha sem flyer nao renderiza img', () => {
    render(<EventCard event={ev({ flyer_url: null })} variant="row" onOpen={() => {}} />)
    expect(screen.queryByRole('img')).toBeNull()
    expect(screen.getByText(/Selva Club/)).toBeInTheDocument()
  })

  it('linha com flyer mostra thumb', () => {
    render(<EventCard event={ev({ flyer_url: '/flyers/T.jpg' })} variant="row" onOpen={() => {}} />)
    expect(screen.getByRole('img')).toHaveAttribute('src', '/flyers/T.jpg')
  })

  it('clique chama onOpen com o evento', async () => {
    const onOpen = vi.fn()
    const e = ev({})
    render(<EventCard event={e} variant="row" onOpen={onOpen} />)
    await userEvent.click(screen.getByText('Mamba Negra'))
    expect(onOpen).toHaveBeenCalledWith(e)
  })
})
