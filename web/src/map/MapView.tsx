import { Map, Marker, Popup } from 'react-map-gl/maplibre'
import { useState } from 'react'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { EventWithGeo } from '../data/join'

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

export function MapView({ events, selectedId, onSelect }: {
  events: EventWithGeo[]; selectedId: number | null; onSelect: (id: number) => void
}) {
  const [popupId, setPopupId] = useState<number | null>(null)
  const mappable = events.filter((e) => e.mappable)
  const popup = mappable.find((e) => e.id === (popupId ?? selectedId))
  return (
    <Map
      initialViewState={{ longitude: -46.63, latitude: -23.55, zoom: 11 }}
      mapStyle={MAP_STYLE}
      style={{ width: '100%', height: '100%' }}
    >
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
    </Map>
  )
}
