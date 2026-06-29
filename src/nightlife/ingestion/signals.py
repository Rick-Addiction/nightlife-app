# src/nightlife/ingestion/signals.py
from __future__ import annotations

from ..domain.scoring import EventSignals, VenueSignals


def derive_venue_signals(source_type: str) -> VenueSignals:
    return VenueSignals(
        google_places_operational=source_type == "google_places",
        osm_match=source_type == "osm",
        official_website=source_type == "official_website",
        instagram_link=source_type == "instagram",
    )


def derive_event_signals(*, source_type: str, has_future_date: bool, venue_matched: bool) -> EventSignals:
    return EventSignals(
        future_date=has_future_date,
        venue_matched=venue_matched,
        official_source=source_type in ("official_website", "organizer"),
        ticketing_source=source_type == "ticketing",
        no_venue=not venue_matched,
    )
