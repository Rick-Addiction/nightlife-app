import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EventDetail } from './EventDetail'
import type { EventWithGeo } from '../data/join'

const ev = (over: Partial<EventWithGeo>): EventWithGeo => ({
  id: 1, name: 'Mamba Negra', starts_at: '2099-07-12T23:00:00-03:00', ends_at: null,
  venue_id: 5, status: 'scheduled', genre: 'Techno', ticket_url: 'https://t/x',
  confidence: 85, effective_confidence: 85, flyer_url: '/flyers/A.jpg',
  venueName: 'Selva Club', venueInstagram: 'selva.011', lat: -23.55, lng: -46.65, mappable: true, ...over,
})

describe('EventDetail', () => {
  it('mostra flyer, info e os 3 botoes com links certos', () => {
    render(<EventDetail event={ev({})} onClose={() => {}} />)
    expect(screen.getByRole('img')).toHaveAttribute('src', '/flyers/A.jpg')
    expect(screen.getByText('Mamba Negra')).toBeInTheDocument()
    expect(screen.getByText(/Selva Club/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /TICKET/ })).toHaveAttribute('href', 'https://t/x')
    expect(screen.getByRole('link', { name: 'IG' })).toHaveAttribute('href', 'https://instagram.com/selva.011')
    expect(screen.getByRole('link', { name: 'MAPA' }))
      .toHaveAttribute('href', 'https://maps.google.com/?q=-23.55,-46.65')
  })

  it('sem ticket/ig/geo esconde os botoes correspondentes', () => {
    render(<EventDetail event={ev({ ticket_url: null, venueInstagram: null, lat: null, lng: null, mappable: false, flyer_url: null })}
                        onClose={() => {}} />)
    expect(screen.queryByRole('link', { name: /TICKET/ })).toBeNull()
    expect(screen.queryByRole('link', { name: 'IG' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'MAPA' })).toBeNull()
    expect(screen.queryByRole('img')).toBeNull()
  })

  it('fechar chama onClose', async () => {
    const onClose = vi.fn()
    render(<EventDetail event={ev({})} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: /fechar|✕/i }))
    expect(onClose).toHaveBeenCalled()
  })
})
