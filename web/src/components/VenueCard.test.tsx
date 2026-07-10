import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { VenueCard } from './VenueCard'
import type { VenueOut } from '../api/types'
import type { EventWithGeo } from '../data/join'

const NOW = new Date(2026, 6, 10, 22, 0)

const base: VenueOut = {
  id: 1, name: 'D-Edge', category: 'nightclub', lat: -23.52, lng: -46.66,
  address: 'Al. Olga 170', instagram: 'dedgeclub', website: 'https://d-edge.com.br',
  status: 'active', confidence: 80, effective_confidence: 80, is_monitored: true,
  ig_last_post_at: null, places_verified: false,
}
function evt(name: string): EventWithGeo {
  return { id: 9, name, starts_at: '2026-07-11T02:00:00Z', ends_at: null, venue_id: 1,
           status: 'scheduled', genre: null, ticket_url: null, flyer_url: null,
           confidence: 50, effective_confidence: 50, venueName: 'D-Edge', venueInstagram: null,
           venueIgLastPostAt: null, lat: -23.52, lng: -46.66, mappable: true } as EventWithGeo
}

describe('VenueCard badges', () => {
  it('✓ VERIFICADO quando places_verified', () => {
    render(<VenueCard venue={{ ...base, places_verified: true }} upcoming={[]}
                      expanded={false} onToggle={() => {}} onOpenEvent={() => {}} now={NOW} />)
    expect(screen.getByText('✓ VERIFICADO')).toBeInTheDocument()
  })
  it('IG HOJE / IG ATIVO conforme ig_last_post_at', () => {
    const { rerender } = render(
      <VenueCard venue={{ ...base, ig_last_post_at: new Date(2026, 6, 10, 9).toISOString() }}
                 upcoming={[]} expanded={false} onToggle={() => {}} onOpenEvent={() => {}} now={NOW} />)
    expect(screen.getByText('IG HOJE')).toBeInTheDocument()
    rerender(
      <VenueCard venue={{ ...base, ig_last_post_at: new Date(2026, 6, 1).toISOString() }}
                 upcoming={[]} expanded={false} onToggle={() => {}} onOpenEvent={() => {}} now={NOW} />)
    expect(screen.getByText('IG ATIVO')).toBeInTheDocument()
  })
  it('contagem de festas futuras', () => {
    render(<VenueCard venue={base} upcoming={[evt('Gop Tun')]} expanded={false}
                      onToggle={() => {}} onOpenEvent={() => {}} now={NOW} />)
    expect(screen.getByText('1 FESTA')).toBeInTheDocument()
  })
  it('expandido mostra endereco, festas clicaveis e links', async () => {
    const onOpenEvent = vi.fn()
    render(<VenueCard venue={base} upcoming={[evt('Gop Tun')]} expanded={true}
                      onToggle={() => {}} onOpenEvent={onOpenEvent} now={NOW} />)
    expect(screen.getByText('Al. Olga 170')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Gop Tun'))
    expect(onOpenEvent).toHaveBeenCalled()
    expect(screen.getByRole('link', { name: 'IG' })).toHaveAttribute(
      'href', 'https://instagram.com/dedgeclub')
    expect(screen.getByRole('link', { name: 'MAPA' })).toHaveAttribute(
      'href', expect.stringContaining('maps.google.com'))
  })
})
