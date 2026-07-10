import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LocaisTab, filterVenues, normalize } from './LocaisTab'
import type { VenueOut } from '../api/types'

function venue(id: number, name: string, address: string | null = null): VenueOut {
  return { id, name, category: 'nightclub', lat: -23.55, lng: -46.66, address,
           instagram: null, website: null, status: 'active', confidence: 50,
           effective_confidence: 50, is_monitored: false,
           ig_last_post_at: null, places_verified: false }
}

describe('busca', () => {
  it('normalize tira acento e caixa', () => {
    expect(normalize('Trackers, R. Augusta')).toBe('trackers, r. augusta')
    expect(normalize('TATUAPÉ')).toBe('tatuape')
  })
  it('filterVenues casa nome OU endereco', () => {
    const vs = [venue(1, 'Selva Club', 'R. Augusta 501'), venue(2, 'D-Edge', 'Al. Olga 170')]
    expect(filterVenues(vs, 'augusta')).toHaveLength(1)
    expect(filterVenues(vs, 'd-edge')).toHaveLength(1)
    expect(filterVenues(vs, '')).toHaveLength(2)
  })
})

describe('LocaisTab', () => {
  it('lista, busca e expande', async () => {
    render(<LocaisTab venues={[venue(1, 'Selva Club', 'R. Augusta 501'), venue(2, 'D-Edge')]}
                      events={[]} onOpenEvent={() => {}} />)
    expect(screen.getByText('Selva Club')).toBeInTheDocument()
    expect(screen.getByText('D-Edge')).toBeInTheDocument()
    await userEvent.type(screen.getByRole('textbox'), 'selva')
    expect(screen.queryByText('D-Edge')).toBeNull()
  })
})
