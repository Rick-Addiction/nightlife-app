import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FestasTab } from './FestasTab'
import { initialFilters } from '../filters/state'
import type { EventWithGeo } from '../data/join'

const ev = (id: number, name: string, flyer: string | null): EventWithGeo => ({
  id, name, starts_at: '2099-07-12T23:00:00-03:00', ends_at: null,
  venue_id: 1, status: 'scheduled', genre: null, ticket_url: null, confidence: 50,
  effective_confidence: 50, flyer_url: flyer, venueName: 'Selva Club', lat: -23.5, lng: -46.6, mappable: true,
})

describe('FestasTab', () => {
  it('manchete por preset + contagem + hero destacado', () => {
    render(<FestasTab events={[ev(1, 'Mamba Negra', '/f/1.jpg'), ev(2, 'Ghost', null)]}
                      filters={{ ...initialFilters, preset: 'today' }} dispatch={() => {}}
                      onOpen={() => {}} />)
    // match EXATO: /ESTA/ (regex) colidiria com "2 FESTAS" (substring)
    expect(screen.getByText('ESTA')).toBeInTheDocument()      // manchete "ESTA NOITE"
    expect(screen.getByText('2 FESTAS')).toBeInTheDocument()  // contador .label separado
    expect(screen.getByRole('img')).toHaveAttribute('src', '/f/1.jpg')  // hero
    expect(screen.getByText('Ghost')).toBeInTheDocument()
  })

  it('vazio mostra estado honesto', () => {
    render(<FestasTab events={[]} filters={initialFilters} dispatch={() => {}} onOpen={() => {}} />)
    expect(screen.getByText(/Nenhuma festa/i)).toBeInTheDocument()
  })
})
