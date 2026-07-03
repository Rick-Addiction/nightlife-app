# src/nightlife/persistence/events_repo.py
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.dedupe import EventKey, compare
from ..models import DedupeCandidate, Event, Venue
from .confidence import (
    EVENT_SOURCE_CONTRIBUTION,
    recompute_event_confidence,
    recompute_venue_confidence,
)
from .evidence import record_event_evidence
from .inputs import EventInput, SourceInfo


def _key_from_input(c: EventInput) -> EventKey:
    return EventKey(name=c.name, starts_at=c.starts_at, venue_name=c.venue_name,
                    organizer=c.organizer, ticket_url=c.ticket_url)


def _key_from_row(e: Event) -> EventKey:
    # organizer so existe quando organizer_id foi linkado (fonte futura fara isso)
    venue_name = e.venue.name if e.venue is not None else None
    organizer = e.organizer.name if e.organizer is not None else None
    return EventKey(name=e.name, starts_at=e.starts_at, venue_name=venue_name,
                    organizer=organizer, ticket_url=e.ticket_url)


def upsert_event(
    session: Session, candidate: EventInput, source: SourceInfo, *, reference: date
) -> Event:
    cand_key = _key_from_input(candidate)
    existing = session.scalars(select(Event)).all()

    best_row = None
    best = None
    for row in existing:
        result = compare(cand_key, _key_from_row(row))
        if best is None or result.score > best.score:
            best, best_row = result, row

    if best is not None and best.decision == "auto_merge":
        event = best_row
        event.last_seen_at = datetime.now(timezone.utc)
        # preenche lacunas sem sobrescrever dados ja existentes:
        # ex. flyer sem data parseavel + pagina de ticketing com startDate real
        event.starts_at = event.starts_at if event.starts_at is not None else candidate.starts_at
        event.ends_at = event.ends_at if event.ends_at is not None else candidate.ends_at
        event.venue_id = event.venue_id if event.venue_id is not None else candidate.venue_id
        event.ticket_url = event.ticket_url or candidate.ticket_url
        event.genre = event.genre or candidate.genre
        event.lineup_text = event.lineup_text or candidate.lineup_text
    else:
        event = Event(
            name=candidate.name, starts_at=candidate.starts_at, ends_at=candidate.ends_at,
            venue_id=candidate.venue_id, lineup_text=candidate.lineup_text,
            genre=candidate.genre, ticket_url=candidate.ticket_url,
            raw_fields=candidate.raw_fields, status="scheduled",
        )
        session.add(event)
        session.flush()
        if best is not None and best.decision == "review":
            session.add(DedupeCandidate(
                kind="event", a_id=event.id, b_id=best_row.id,
                similarity_score=best.score, decision="review",
            ))

    record_event_evidence(
        session, event.id, source,
        contribution=EVENT_SOURCE_CONTRIBUTION.get(source.source_type, 0),
    )
    recompute_event_confidence(session, event, reference=reference)
    # um evento futuro linkado muda o sinal future_event_linked do venue
    if event.venue_id is not None:
        venue = session.get(Venue, event.venue_id)
        if venue is not None:
            recompute_venue_confidence(session, venue, reference=reference)
    return event
