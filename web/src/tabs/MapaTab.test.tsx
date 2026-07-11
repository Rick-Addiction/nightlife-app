import { describe, it, expect, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { EventWithGeo } from '../data/join'
import type { VenueOut } from '../api/types'

const mapProps = vi.fn()
vi.mock('../map/MapView', () => ({
  MapView: (props: Record<string, unknown>) => { mapProps(props); return <div data-testid="map-stub" /> },
}))
vi.mock('../api/sweep', () => ({
  startSweep: vi.fn(async () => ({ id: 1 })),
  fetchCurrentSweep: vi.fn(async () => { throw new Error('404') }),
}))

import { MapaTab, visibleVenues } from './MapaTab'
import { initialFilters } from '../filters/state'
import { fetchCurrentSweep, type SweepOut } from '../api/sweep'

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
    withDrawer: true, onDataStale: () => {},
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
  it('evento sem data nao vira marker no mapa (mas segue na gaveta)', () => {
    const dated = evt(1, 10, new Date(2026, 6, 10, 23, 0).toISOString())
    const undated = { ...evt(2, 10, new Date().toISOString()), starts_at: null } as EventWithGeo
    render(<MapaTab {...base} events={[dated, undated]} />)
    const last = mapProps.mock.calls.at(-1)![0] as { events: { id: number }[] }
    expect(last.events.map((e) => e.id)).toEqual([1])
    expect(screen.getByText(/2 FESTAS NA ÁREA/)).toBeInTheDocument()
  })
  it('botao VARRER AREA entra em modo alvo e o clique confirma o circulo', async () => {
    render(<MapaTab {...base} />)
    await userEvent.click(screen.getByRole('button', { name: '⌖ VARRER ÁREA' }))
    const last = mapProps.mock.calls.at(-1)![0] as { onPickPoint?: (a: number, b: number) => void }
    expect(last.onPickPoint).toBeDefined()
    act(() => last.onPickPoint!(-23.553, -46.656))
    expect(await screen.findByRole('button', { name: /VARRER \d+ PERFIS/ })).toBeInTheDocument()
  })
  it('poll do sweep dispara onDataStale uma vez quando o run termina (W8)', async () => {
    vi.useFakeTimers()
    try {
      const onDataStale = vi.fn()
      const running: SweepOut = {
        id: 1, label: null, status: 'running', phase: 'varrendo', total_handles: 10,
        done_handles: 3, report: [], diff: null, error: null,
        started_at: '2026-07-10T20:00:00Z', finished_at: null,
      }
      const done: SweepOut = {
        ...running, status: 'done', phase: 'done', done_handles: 10,
        diff: { novas_festas: 1, venues_com_pin_novo: [] }, finished_at: new Date().toISOString(),
      }
      vi.mocked(fetchCurrentSweep).mockReset()
      vi.mocked(fetchCurrentSweep)
        .mockResolvedValueOnce(running)
        .mockResolvedValueOnce(done)

      render(<MapaTab {...base} onDataStale={onDataStale} />)
      await act(async () => { await Promise.resolve() })  // deixa o 1o tick (running) resolver
      expect(onDataStale).not.toHaveBeenCalled()

      await act(async () => { await vi.advanceTimersByTimeAsync(5000) })

      expect(onDataStale).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
      vi.mocked(fetchCurrentSweep).mockReset()
      vi.mocked(fetchCurrentSweep).mockImplementation(async () => { throw new Error('404') })
    }
  })
})
