# src/nightlife/ingestion/base.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Protocol


@dataclass
class RawVenue:
    name: str
    source_type: str
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    category: str | None = None
    source_url: str | None = None
    raw_payload: str = ""


@dataclass
class RawEventPage:
    kind: str          # "jsonld" | "html" | "freetext"
    content: str
    source_type: str
    source_url: str | None = None


@dataclass
class RawEvent:
    """Evento JA estruturado (ex.: API de ticketing) — dispensa extracao.

    O venue vem EMBUTIDO (nome/endereco/geo) para o pipeline upsertar e ancorar.
    """
    name: str
    source_type: str                    # "ticketing"
    starts_at: datetime | None = None   # tz-aware (UTC da API)
    ends_at: datetime | None = None
    venue: RawVenue | None = None
    venue_name: str | None = None       # so ANCORA em venue existente (flyer: nome sem geo)
    lineup_text: str | None = None
    organizer_name: str | None = None
    genre: str | None = None
    ticket_url: str | None = None
    source_url: str | None = None
    raw_payload: str = ""


class Source(Protocol):
    def venues(self) -> Iterable[RawVenue]: ...
    def event_pages(self) -> Iterable[RawEventPage]: ...
    def events(self) -> Iterable[RawEvent]: ...
