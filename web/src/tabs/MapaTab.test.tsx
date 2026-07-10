import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { EventWithGeo } from '../data/join'
import type { VenueOut } from '../api/types'

const mapProps = vi.fn()
vi.mock('../map/MapView', () => ({
  MapView: (props: Record<string, unknown>) => { mapProps(props); return <div data-testid="map-stub" /> },
}))

import { MapaTab, visibleVenues } from './MapaTab'
import { initialFilters } from '../filters/state'

const NOW = new Date(2026, 6, 10, 22, 0)

function venue(id: number): VenueOut {
  return { id, name: `V${id}`, category: null, lat: -23.55, lng: -46.66, address: null,
           instagram: null, website: null, status: 'active', confidence: 50,
           effective_confidence: 50, is_monitored: false,
           ig_last_post_at: null, places_verified: false }
}
function evt(id: number, venueId: number, startsAt: string): EventWithGeo {
  return { id, name: `E${id}`, starts_at: startsAt, ends_at: null, venue_id: venueId,
           status: 'scheduled', genre: null, ticket_url: null, flyer_url: null,
           confidence: 50, effective_confidence: 50, venueName: null, venueInstagram: null,
           venueIgLastPostAt: null, lat: -23.55, lng: -46.66, mappable: true } as EventWithGeo
}

describe('visibleVenues', () => {
  it('hojeOnly filtra para venues com festa no dia local', () => {
    const evs = [evt(1, 10, new Date(2026, 6, 10, 23, 0).toISOString()),
                 evt(2, 20, new Date(2026, 6, 12, 23, 0).toISOString())]
    const vns = [venue(10), venue(20), venue(30)]
    expect(visibleVenues(vns, evs, { festas: true, locais: true, hojeOnly: false }, NOW)).toHaveLength(3)
    expect(visibleVenues(vns, evs, { festas: true, locais: true, hojeOnly: true }, NOW)
      .map((v) => v.id)).toEqual([10])
  })
})

describe('MapaTab', () => {
  const base = {
    events: [evt(1, 10, new Date(2026, 6, 10, 23, 0).toISOString())],
    venues: [venue(10)], filters: initialFilters, dispatch: () => {},
    selectedId: null, onSelect: () => {}, onOpenSheet: () => {}, activeCount: 0,
    withDrawer: true,
  }
  it('desligar FESTAS zera os events do MapView', async () => {
    render(<MapaTab {...base} />)
    await userEvent.click(screen.getByRole('button', { name: 'CAMADAS' }))
    await userEvent.click(screen.getByRole('button', { name: '◆ FESTAS' }))
    const last = mapProps.mock.calls.at(-1)![0] as { events: unknown[] }
    expect(last.events).toHaveLength(0)
  })
  it('desligar LOCAIS derruba showVenues', async () => {
    render(<MapaTab {...base} />)
    await userEvent.click(screen.getByRole('button', { name: 'CAMADAS' }))
    await userEvent.click(screen.getByRole('button', { name: '■ LOCAIS' }))
    const last = mapProps.mock.calls.at(-1)![0] as { showVenues: boolean }
    expect(last.showVenues).toBe(false)
  })
  it('com withDrawer renderiza a gaveta com a contagem', () => {
    render(<MapaTab {...base} />)
    expect(screen.getByText(/1 FESTA NA ÁREA/)).toBeInTheDocument()
  })
})
