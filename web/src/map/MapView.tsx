import { Map, Marker, Popup, Source, Layer } from 'react-map-gl/maplibre'
import type { MapLayerMouseEvent } from 'react-map-gl/maplibre'
import { useState, useMemo, useEffect } from 'react'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { EventWithGeo } from '../data/join'
import type { VenueOut } from '../api/types'
import { venuesToFeatureCollection } from './geojson'
import { upcomingEventsAtVenue } from '../data/venueEvents'

const MAP_STYLE = {
  version: 8 as const,
  sources: {
    carto: {
      type: 'raster' as const,
      tiles: ['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap © CARTO',
    },
  },
  layers: [{ id: 'carto', type: 'raster' as const, source: 'carto' }],
}

type SelVenue = { id: number; name: string; category: string | null; lng: number; lat: number }

function fmtDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
}

export function MapView({ events, venues, selectedId, onSelect, showVenues }: {
  events: EventWithGeo[]; venues: VenueOut[]; selectedId: number | null
  onSelect: (id: number) => void; showVenues: boolean
}) {
  const [popupId, setPopupId] = useState<number | null>(null)
  const [selVenue, setSelVenue] = useState<SelVenue | null>(null)
  const mappable = events.filter((e) => e.mappable)
  const popup = mappable.find((e) => e.id === (popupId ?? selectedId))
  // recriar a FeatureCollection a cada render forcaria um deepEqual sobre ~800
  // features; memoiza pra so recalcular quando os venues mudam.
  const venuesFC = useMemo(() => venuesToFeatureCollection(venues), [venues])
  // desligar a camada deve fechar o popup do venue (senao fica pendurado)
  useEffect(() => { if (!showVenues) setSelVenue(null) }, [showVenues])

  const onMapClick = (e: MapLayerMouseEvent) => {
    const f = e.features?.[0]
    // aceita a camada base e o halo do selecionado (ambos carregam a prop id)
    if (f && (f.layer.id === 'venue-dots' || f.layer.id === 'venue-sel') && f.geometry.type === 'Point') {
      const [lng, lat] = f.geometry.coordinates as [number, number]
      const p = f.properties as { id: number; name: string; category: string | null }
      setSelVenue({ id: p.id, name: p.name, category: p.category, lng, lat })
    } else {
      setSelVenue(null)
    }
  }

  const venueEvents = selVenue ? upcomingEventsAtVenue(events, selVenue.id) : []

  return (
    <Map
      initialViewState={{ longitude: -46.63, latitude: -23.55, zoom: 11 }}
      mapStyle={MAP_STYLE}
      style={{ width: '100%', height: '100%' }}
      interactiveLayerIds={showVenues ? ['venue-dots', 'venue-sel'] : []}
      onClick={onMapClick}
      // container flex dimensiona depois do mount; um resize garante que as
      // camadas GL pintem (os Markers DOM projetam mesmo sem isso)
      onLoad={(e) => e.target.resize()}
    >
      {showVenues && (
        <Source id="venues-src" type="geojson" data={venuesFC}>
          <Layer id="venue-dots" type="circle" paint={{
            'circle-radius': 3.5,
            'circle-color': '#5a6b8a',
            'circle-opacity': 0.7,
          }} />
          <Layer id="venue-sel" type="circle"
                 filter={['==', ['get', 'id'], selVenue?.id ?? -1]}
                 paint={{ 'circle-radius': 7, 'circle-color': '#8fb0ff', 'circle-opacity': 0.95 }} />
        </Source>
      )}

      {mappable.map((e) => (
        <Marker key={e.id} longitude={e.lng!} latitude={e.lat!} anchor="bottom"
                onClick={(ev) => { ev.originalEvent.stopPropagation(); onSelect(e.id); setPopupId(e.id) }}>
          <div style={{
            width: 12, height: 12, borderRadius: '50%',
            background: e.id === selectedId ? '#e055c0' : '#22e0e0',
            boxShadow: `0 0 8px ${e.id === selectedId ? '#e055c0' : '#22e0e0'}`,
            cursor: 'pointer',
          }} />
        </Marker>
      ))}

      {popup && (
        <Popup longitude={popup.lng!} latitude={popup.lat!} anchor="top"
               onClose={() => setPopupId(null)} closeButton={false}>
          <strong>{popup.name}</strong><br />{popup.venueName}
        </Popup>
      )}

      {selVenue && (
        <Popup longitude={selVenue.lng} latitude={selVenue.lat} anchor="top"
               onClose={() => setSelVenue(null)} closeButton={true} maxWidth="240px">
          <strong>{selVenue.name}</strong>
          {selVenue.category && <div style={{ opacity: 0.7 }}>{selVenue.category}</div>}
          {venueEvents.length > 0 ? (
            <ul style={{ margin: '6px 0 0', paddingLeft: 16 }}>
              {venueEvents.slice(0, 5).map((e) => (
                <li key={e.id}>{fmtDate(e.starts_at)} — {e.name}</li>
              ))}
            </ul>
          ) : (
            <div style={{ opacity: 0.6, marginTop: 6 }}>sem eventos futuros</div>
          )}
          {(() => {
            const v = venues.find((x) => x.id === selVenue.id)
            return (
              <div style={{ marginTop: 6, display: 'flex', gap: 8 }}>
                {v?.instagram && <a href={`https://instagram.com/${v.instagram}`} target="_blank" rel="noreferrer">IG</a>}
                {v?.website && <a href={v.website} target="_blank" rel="noreferrer">site</a>}
              </div>
            )
          })()}
        </Popup>
      )}
    </Map>
  )
}
