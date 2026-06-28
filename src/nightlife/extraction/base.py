# src/nightlife/extraction/base.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ExtractedEvent:
    name: str | None = None
    starts_at_raw: str | None = None
    starts_at: datetime | None = None
    ends_at_raw: str | None = None
    venue_name: str | None = None
    address: str | None = None
    organizer: str | None = None
    lineup_text: str | None = None
    genre: str | None = None
    ticket_url: str | None = None
    price_raw: str | None = None
    source_url: str | None = None
    raw: dict = field(default_factory=dict)
    field_confidence: dict = field(default_factory=dict)


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime (Schema.org style), tolerating a trailing 'Z'."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
