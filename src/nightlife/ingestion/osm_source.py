# src/nightlife/ingestion/osm_source.py
from __future__ import annotations

import json

import httpx

from .base import RawEvent, RawEventPage, RawVenue

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
# bbox da cidade de Sao Paulo: (south, west, north, east)
SP_BBOX = (-24.00, -46.83, -23.36, -46.36)
_USER_AGENT = "nightlife-app/0.1 (uso pessoal; contato: henrique.rachti@gmail.com)"


def _build_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    bb = f"{s},{w},{n},{e}"
    return (
        "[out:json][timeout:60];"
        f'(nwr["amenity"="nightclub"]({bb});'
        f'nwr["amenity"="events_venue"]({bb}););'
        "out center tags;"
    )


def parse_overpass(data: dict) -> list[RawVenue]:
    """JSON do Overpass -> RawVenues. Puro: testavel sem rede.

    Descarta elementos sem `name` ou sem coordenada utilizavel (node sem
    lat/lon e way/relation sem `center`).
    """
    out: list[RawVenue] = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        lat, lng = el.get("lat"), el.get("lon")
        if lat is None or lng is None:
            center = el.get("center") or {}
            lat, lng = center.get("lat"), center.get("lon")
        if lat is None or lng is None:
            continue
        street = tags.get("addr:street")
        number = tags.get("addr:housenumber")
        address = f"{street}, {number}" if street and number else street
        out.append(RawVenue(
            name=name,
            source_type="osm",
            lat=lat,
            lng=lng,
            address=address,
            category=tags.get("amenity"),
            source_url=f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
            # sort_keys: hash de payload estavel entre execucoes (idempotencia)
            raw_payload=json.dumps(el, ensure_ascii=False, sort_keys=True),
        ))
    return out


class OSMSource:
    """Fonte real #1: venues de nightlife de SP via Overpass API (OSM)."""

    def __init__(self, *, endpoint: str = OVERPASS_ENDPOINT,
                 bbox: tuple[float, float, float, float] = SP_BBOX,
                 timeout: float = 90.0) -> None:
        self._endpoint = endpoint
        self._bbox = bbox
        self._timeout = timeout

    def venues(self) -> list[RawVenue]:
        resp = httpx.post(
            self._endpoint,
            data={"data": _build_query(self._bbox)},
            headers={"User-Agent": _USER_AGENT},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return parse_overpass(resp.json())

    def event_pages(self) -> list[RawEventPage]:
        return []

    def events(self) -> list[RawEvent]:
        return []
