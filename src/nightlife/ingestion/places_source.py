"""Source de descoberta geografica via Google Places Nearby (spec §4B).

Itera pontos-semente dos bairros de balada de SP x tipos de nightlife, chama o
PlacesClient e devolve RawVenue com geo + place_id (identidade estavel para o
dedup). event_venue foi descartado no design (ruido: buffet/casamento)."""
from __future__ import annotations

from typing import Callable, Iterable

from .base import RawEvent, RawEventPage, RawVenue
from .places_client import PlacesClient

SEARCH_TYPES = ("night_club", "dance_hall", "live_music_venue", "concert_hall")

# centroides aproximados de bairros de balada de SP (precisao coberta pelo raio)
SEED_POINTS: list[tuple[str, float, float]] = [
    ("Augusta/Consolacao", -23.5545, -46.6620),
    ("Vila Madalena",      -23.5560, -46.6900),
    ("Barra Funda",        -23.5260, -46.6640),
    ("Lapa",               -23.5230, -46.7050),
    ("Itaim/Vila Olimpia", -23.5850, -46.6790),
    ("Pinheiros",          -23.5670, -46.6950),
    ("Centro/Republica",   -23.5440, -46.6420),
    ("Bela Vista/Bexiga",  -23.5580, -46.6450),
    ("Vila Mariana",       -23.5890, -46.6340),
    ("Moema",              -23.6000, -46.6650),
    ("Santana",            -23.5030, -46.6250),
    ("Tatuape",            -23.5400, -46.5760),
    ("Brooklin/Berrini",   -23.6100, -46.6900),
    ("Perdizes/Pompeia",   -23.5320, -46.6820),
]
_SEARCH_RADIUS_M = 1000

_NIGHTCLUB_TYPES = {"night_club", "dance_hall", "live_music_venue", "concert_hall"}


def _category_for(primary_type: str | None) -> str:
    return "nightclub" if primary_type in _NIGHTCLUB_TYPES else "bar"


class PlacesSource:
    def __init__(self, client: PlacesClient, *, seeds=SEED_POINTS,
                 types=SEARCH_TYPES, radius: float = _SEARCH_RADIUS_M,
                 log: Callable[[str], None] = print) -> None:
        self._client = client
        self._seeds = seeds
        self._types = types
        self._radius = radius
        self._log = log

    def venues(self) -> Iterable[RawVenue]:
        for name, lat, lng in self._seeds:
            for t in self._types:
                results = self._client.search_nearby(lat, lng, self._radius, t)
                if len(results) >= 20:
                    self._log(f"[places] saturou 20 em {name!r}/{t} (sinal p/ grade futura)")
                for r in results:
                    yield RawVenue(
                        name=r.name, source_type="google_places",
                        lat=r.lat, lng=r.lng, address=r.address,
                        category=_category_for(r.primary_type), source_url=r.place_id,
                    )

    def event_pages(self) -> Iterable[RawEventPage]:
        return []

    def events(self) -> Iterable[RawEvent]:
        return []
