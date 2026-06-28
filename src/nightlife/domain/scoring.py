# src/nightlife/domain/scoring.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VenueSignals:
    google_places_operational: bool = False
    osm_match: bool = False
    official_website: bool = False
    instagram_link: bool = False
    future_event_linked: bool = False
    closed: bool = False
    permanently_closed: bool = False
    stale: bool = False
    unverified: bool = False


@dataclass
class EventSignals:
    future_date: bool = False
    venue_matched: bool = False
    official_source: bool = False        # site oficial do venue OU do organizador
    ticketing_source: bool = False
    independent_source_count: int = 1
    ambiguous_date: bool = False
    no_venue: bool = False
    past_date: bool = False
    cancelled: bool = False
    weak_source: bool = False


def score_venue(s: VenueSignals) -> int:
    score = 0
    if s.google_places_operational:
        score += 30
    if s.osm_match:
        score += 20
    if s.official_website:
        score += 20
    if s.instagram_link:
        score += 15
    if s.future_event_linked:
        score += 15
    if s.closed:
        score -= 20
    if s.permanently_closed:
        score -= 50
    if s.stale:
        score -= 10
    if s.unverified:
        score -= 15
    return max(0, score)


def score_event(s: EventSignals) -> int:
    score = 0
    if s.future_date:
        score += 20
    if s.venue_matched:
        score += 20
    if s.official_source:
        score += 25
    if s.ticketing_source:
        score += 25
    if s.independent_source_count >= 2:
        score += 20
    if s.ambiguous_date:
        score -= 10
    if s.no_venue:
        score -= 20
    if s.past_date:
        score -= 30
    if s.cancelled:
        score -= 50
    if s.weak_source:
        score -= 15
    return max(0, score)
