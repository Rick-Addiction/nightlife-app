# src/nightlife/persistence/events_repo.py
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.dedupe import EventKey, compare
from ..domain.scoring import EventSignals, score_event
from ..models import DedupeCandidate, Event, EventSource
from ._utils import payload_hash
from .inputs import EventInput, SourceInfo


def _key_from_input(c: EventInput) -> EventKey:
    return EventKey(name=c.name, starts_at=c.starts_at, venue_name=c.venue_name,
                    organizer=c.organizer, ticket_url=c.ticket_url)


def _key_from_row(e: Event) -> EventKey:
    # organizer so existe quando organizer_id foi linkado (o pipeline do Plano C fara isso);
    # no esqueleto e.organizer e None, entao a dimensao organizer do dedupe fica inativa.
    venue_name = e.venue.name if e.venue is not None else None
    organizer = e.organizer.name if e.organizer is not None else None
    return EventKey(name=e.name, starts_at=e.starts_at, venue_name=venue_name,
                    organizer=organizer, ticket_url=e.ticket_url)


def upsert_event(
    session: Session, candidate: EventInput, source: SourceInfo, signals: EventSignals
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
        # uma nova fonte so pode REFORCAR a confianca, nunca rebaixar
        event.confidence = max(event.confidence, score_event(signals))
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
        event.confidence = score_event(signals)

    session.add(EventSource(
        event_id=event.id,
        source_type=source.source_type,
        source_url=source.source_url,
        raw_payload_hash=payload_hash(source.raw_payload),
        extracted_fields=source.extracted_fields,
        confidence_contribution=event.confidence,
    ))
    return event
