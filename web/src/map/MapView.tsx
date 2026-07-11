import { Map, Marker, Popup, Source, Layer } from 'react-map-gl/maplibre'
import type { MapLayerMouseEvent } from 'react-map-gl/maplibre'
import { useState, useMemo, useEffect } from 'react'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { EventWithGeo } from '../data/join'
import type { VenueOut } from '../api/types'
import { venuesToFeatureCollection } from './geojson'
import { circleGeoJSON } from './sweep'
import { upcomingEventsAtVenue } from '../data/venueEvents'
import { fmtDate as fmtDateFull } from '../components/EventCard'

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

export function MapView({ events, venues, selectedId, onSelect, showVenues,
                          onPickPoint, circle }: {
  events: EventWithGeo[]; venues: VenueOut[]; selectedId: number | null
  onSelect: (id: number) => void; showVenues: boolean
  onPickPoint?: (lat: number, lng: number) => void
  circle?: { lat: number; lng: number; km: number } | null
}) {
  const [popupId, setPopupId] = useState<number | null>(null)
  const [selVenue, setSelVenue] = useState<SelVenue | null>(null)
  const mappable = events.filter((e) => e.mappable)
  const popup = mappable.find((e) => e.id === popupId)
  // recriar a FeatureCollection a cada render forcaria um deepEqual sobre ~800
  // features; memoiza pra so recalcular quando os venues mudam.
  const venuesFC = useMemo(() => venuesToFeatureCollection(venues), [venues])
  // desligar a camada deve fechar o popup do venue (senao fica pendurado)
  useEffect(() => { if (!showVenues) setSelVenue(null) }, [showVenues])

  const onMapClick = (e: MapLayerMouseEvent) => {
    if (onPickPoint) {
      onPickPoint(e.lngLat.lat, e.lngLat.lng)
      return
    }
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
            'circle-color': '#00ff85',
            'circle-opacity': 0.45,
          }} />
          <Layer id="venue-sel" type="circle"
                 filter={['==', ['get', 'id'], selVenue?.id ?? -1]}
                 paint={{ 'circle-radius': 7, 'circle-color': '#00ff85', 'circle-opacity': 0.95 }} />
        </Source>
      )}

      {circle && (
        <Source id="sweep-circle-src" type="geojson"
                data={circleGeoJSON(circle.lat, circle.lng, circle.km)}>
          <Layer id="sweep-circle-fill" type="fill"
                 paint={{ 'fill-color': '#ff2e88', 'fill-opacity': 0.12 }} />
          <Layer id="sweep-circle-line" type="line"
                 paint={{ 'line-color': '#ff2e88', 'line-width': 2 }} />
        </Source>
      )}

      {mappable.map((e) => (
        <Marker key={e.id} longitude={e.lng!} latitude={e.lat!} anchor="bottom"
                onClick={(ev) => {
                  // clique no pin abre o MINI-CARD ancorado no ponto (nao a
                  // sheet de tela cheia — pesado demais pra um clique no mapa)
                  ev.originalEvent.stopPropagation()
                  setSelVenue(null)
                  setPopupId(e.id)
                }}>
          <div style={{
            width: 13, height: 13,
            background: e.id === popupId || e.id === selectedId ? 'var(--green)' : 'var(--pink)',
            transform: 'rotate(45deg)', border: '2px solid #000',
            cursor: 'pointer',
          }} />
        </Marker>
      ))}

      {popup && (
        <Popup longitude={popup.lng!} latitude={popup.lat!} anchor="bottom" offset={16}
               onClose={() => setPopupId(null)} closeButton={false} maxWidth="270px">
          <div style={{ display: 'flex', gap: 8, padding: 8, alignItems: 'center', cursor: 'pointer' }}
               onClick={() => onSelect(popup.id)}>
            {popup.flyer_url && (
              <img src={popup.flyer_url} alt="" loading="lazy"
                   style={{ width: 46, height: 46, objectFit: 'cover', flex: 'none' }} />
            )}
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 900, fontSize: 12, textTransform: 'uppercase',
                            letterSpacing: '-0.02em' }}>{popup.name}</div>
              <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 700 }}>
                {fmtDateFull(popup.starts_at)}{popup.venueName ? ` · ${popup.venueName}` : ''}
              </div>
              <div style={{ fontSize: 10, color: 'var(--green)', fontWeight: 900, marginTop: 2 }}>VER →</div>
            </div>
          </div>
        </Popup>
      )}

      {selVenue && (
        <Popup longitude={selVenue.lng} latitude={selVenue.lat} anchor="bottom" offset={10}
               onClose={() => setSelVenue(null)} closeButton={true} maxWidth="250px">
          <div style={{ padding: '10px 12px' }}>
            <div style={{ fontWeight: 900, fontSize: 13, textTransform: 'uppercase',
                          letterSpacing: '-0.02em', paddingRight: 14 }}>{selVenue.name}</div>
            {selVenue.category && (
              <div style={{ fontSize: 9, color: 'var(--green)', fontWeight: 800,
                            textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: 2 }}>
                {selVenue.category}
              </div>
            )}
            {venueEvents.length > 0 ? (
              <div style={{ marginTop: 7 }}>
                {venueEvents.slice(0, 5).map((e) => (
                  <div key={e.id} style={{ fontSize: 10, fontWeight: 700, marginTop: 3 }}>
                    <span style={{ color: 'var(--pink)' }}>{fmtDate(e.starts_at)}</span> {e.name}
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 700, marginTop: 7 }}>
                SEM FESTA MARCADA
              </div>
            )}
            {(() => {
              const v = venues.find((x) => x.id === selVenue.id)
              if (!v?.instagram && !v?.website) return null
              return (
                <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
                  {v?.instagram && (
                    <a className="chip grn" style={{ fontSize: 9, padding: '3px 8px' }}
                       href={`https://instagram.com/${v.instagram}`} target="_blank" rel="noreferrer">IG</a>
                  )}
                  {v?.website && (
                    <a className="chip" style={{ fontSize: 9, padding: '3px 8px' }}
                       href={v.website} target="_blank" rel="noreferrer">SITE</a>
                  )}
                </div>
              )
            })()}
          </div>
        </Popup>
      )}
    </Map>
  )
}
