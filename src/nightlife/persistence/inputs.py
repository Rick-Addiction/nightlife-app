# src/nightlife/persistence/inputs.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SourceInfo:
    source_type: str
    source_url: str | None = None
    raw_payload: str = ""
    extracted_fields: dict = field(default_factory=dict)


@dataclass
class VenueInput:
    name: str
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    category: str | None = None


@dataclass
class EventInput:
    name: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    venue_id: int | None = None
    venue_name: str | None = None
    organizer: str | None = None
    organizer_id: int | None = None
    lineup_text: str | None = None
    genre: str | None = None
    ticket_url: str | None = None
    raw_fields: dict = field(default_factory=dict)
