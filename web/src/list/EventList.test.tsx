import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EventList } from './EventList'
import type { EventWithGeo } from '../data/join'

const base: EventWithGeo = {
  id: 1, name: 'Mamba Negra', starts_at: '2099-06-13T23:00:00-03:00', ends_at: null,
  venue_id: 10, status: 'scheduled', genre: 'techno', ticket_url: 'http://t', flyer_url: null, confidence: 80,
  effective_confidence: 80, venueName: 'Lab Club', lat: -23.5, lng: -46.6, mappable: true,
}

describe('EventList', () => {
  it('renderiza nome, venue, genero e confidence', () => {
    render(<EventList events={[base]} selectedId={null} onSelect={() => {}} />)
    expect(screen.getByText('Mamba Negra')).toBeInTheDocument()
    expect(screen.getByText(/Lab Club/)).toBeInTheDocument()
    expect(screen.getByText('80')).toBeInTheDocument()
  })
  it('marca evento sem geo com selo de local a confirmar', () => {
    render(<EventList events={[{ ...base, mappable: false, venueName: null }]} selectedId={null} onSelect={() => {}} />)
    expect(screen.getByText(/local a confirmar/i)).toBeInTheDocument()
  })
  it('estado vazio', () => {
    render(<EventList events={[]} selectedId={null} onSelect={() => {}} />)
    expect(screen.getByText(/nenhum evento/i)).toBeInTheDocument()
  })
})
