# src/nightlife/persistence/confidence.py
from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.scoring import EventSignals, VenueSignals, score_event, score_venue
from ..models import Event, EventSource, Venue, VenueSource, VerificationLog

# "Dia" do sistema = dia em America/Sao_Paulo (spec sympla §6). A API da
# Sympla entrega UTC; sem converter, festa de sabado 23h viraria "domingo".
_SP_TZ = ZoneInfo("America/Sao_Paulo")

# Quanto cada fonte vale SOZINHA (gravado em confidence_contribution — agora o
# nome e honesto). O score da entidade vem de score_venue/score_event sobre os
# sinais derivados da evidencia acumulada, nao da soma destes valores.
VENUE_SOURCE_CONTRIBUTION = {
    "google_places": 30, "osm": 20, "official_website": 20, "instagram": 15,
}
EVENT_SOURCE_CONTRIBUTION = {
    "ticketing": 25, "official_website": 25, "organizer": 25,
}


def venue_signals_from_evidence(session: Session, venue: Venue, *, reference: date) -> VenueSignals:
    types = set(session.scalars(
        select(VenueSource.source_type).where(VenueSource.venue_id == venue.id)
    ))
    has_future_event = session.scalars(
        select(Event.id).where(Event.venue_id == venue.id, Event.starts_at >= reference).limit(1)
    ).first() is not None
    return VenueSignals(
        google_places_operational="google_places" in types,
        osm_match="osm" in types,
        official_website="official_website" in types,
        instagram_link="instagram" in types,
        future_event_linked=has_future_event,
        closed=venue.status == "closed",
        permanently_closed=venue.status == "permanently_closed",
        # stale/unverified ficam False no v1: frescor e decay na leitura
    )


def event_signals_from_evidence(session: Session, event: Event, *, reference: date) -> EventSignals:
    types = set(session.scalars(
        select(EventSource.source_type).where(EventSource.event_id == event.id)
    ))
    starts = event.starts_at
    return EventSignals(
        future_date=starts is not None and starts.astimezone(_SP_TZ).date() >= reference,
        venue_matched=event.venue_id is not None,
        official_source=bool(types & {"official_website", "organizer"}),
        ticketing_source="ticketing" in types,
        # COUNT DISTINCT source_type como proxy de independencia: 2 posts do
        # mesmo IG nao contam como 2 fontes
        independent_source_count=len(types) or 1,
        no_venue=event.venue_id is None,
        past_date=starts is not None and starts.astimezone(_SP_TZ).date() < reference,
        cancelled=event.status == "cancelled",
    )


def _log_change(session: Session, entity_type: str, entity_id: int, old: int, new: int) -> None:
    session.add(VerificationLog(
        entity_type=entity_type, entity_id=entity_id,
        note=f"confidence {old} -> {new} (recompute)",
    ))


def recompute_venue_confidence(session: Session, venue: Venue, *, reference: date) -> int:
    new = score_venue(venue_signals_from_evidence(session, venue, reference=reference))
    if new != venue.confidence:
        _log_change(session, "venue", venue.id, venue.confidence, new)
        venue.confidence = new
    return venue.confidence


def recompute_event_confidence(session: Session, event: Event, *, reference: date) -> int:
    new = score_event(event_signals_from_evidence(session, event, reference=reference))
    if new != event.confidence:
        _log_change(session, "event", event.id, event.confidence, new)
        event.confidence = new
    return event.confidence
