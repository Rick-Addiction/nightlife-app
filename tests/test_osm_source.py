# tests/test_osm_source.py
from nightlife.ingestion.base import RawVenue
from nightlife.ingestion.mock_source import MockSource  # noqa: F401 (referencia de padrao)
from nightlife.ingestion.osm_source import OSMSource, parse_overpass

OVERPASS_JSON = {
    "elements": [
        {  # node completo
            "type": "node", "id": 111, "lat": -23.5613, "lon": -46.6565,
            "tags": {"amenity": "nightclub", "name": "Lab Club",
                     "addr:street": "R. Augusta", "addr:housenumber": "1000"},
        },
        {  # way com center (sem lat/lon proprios)
            "type": "way", "id": 222,
            "center": {"lat": -23.529, "lon": -46.672},
            "tags": {"amenity": "events_venue", "name": "Audio SP"},
        },
        {  # sem name -> descartado
            "type": "node", "id": 333, "lat": -23.5, "lon": -46.6,
            "tags": {"amenity": "nightclub"},
        },
        {  # sem coordenada utilizavel -> descartado
            "type": "relation", "id": 444,
            "tags": {"amenity": "events_venue", "name": "Fantasma"},
        },
    ]
}


def test_parse_overpass_maps_and_discards():
    venues = parse_overpass(OVERPASS_JSON)
    assert [v.name for v in venues] == ["Lab Club", "Audio SP"]
    lab, audio = venues
    assert isinstance(lab, RawVenue)
    assert lab.source_type == "osm" and lab.category == "nightclub"
    assert (lab.lat, lab.lng) == (-23.5613, -46.6565)
    assert lab.address == "R. Augusta, 1000"
    assert lab.source_url == "https://www.openstreetmap.org/node/111"
    assert audio.lat == -23.529 and audio.address is None  # veio do center
    assert audio.source_url == "https://www.openstreetmap.org/way/222"


def test_osm_source_events_and_pages_are_empty():
    src = OSMSource()
    assert src.event_pages() == []
    assert src.events() == []
