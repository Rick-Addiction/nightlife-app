# src/nightlife/ingestion/pipeline.py
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.matching import VenueRef, match_venue
from ..extraction.freetext import extract_freetext_deterministic
from ..extraction.html_patterns import parse_html_patterns
from ..extraction.jsonld import parse_jsonld_events
from ..models import IngestionRun, Venue
from ..persistence.events_repo import upsert_event
from ..persistence.inputs import EventInput, SourceInfo, VenueInput
from ..persistence.venues_repo import upsert_venue
from .base import RawEventPage, Source
from .signals import derive_event_signals, derive_venue_signals


def _extract_page(page: RawEventPage, reference: date):
    if page.kind == "jsonld":
        return parse_jsonld_events(page.content, source_url=page.source_url)
    if page.kind == "html":
        return parse_html_patterns(page.content, source_url=page.source_url)
    return [extract_freetext_deterministic(page.content, reference=reference, source_url=page.source_url)]


def _resolve_venue(session: Session, venue_name: str | None) -> Venue | None:
    if not venue_name:
        return None
    existing = session.scalars(select(Venue)).all()
    refs = [VenueRef(v.id, v.name, v.address, v.lat, v.lng) for v in existing]
    m = match_venue(VenueRef(None, venue_name), refs)
    return session.get(Venue, m.venue.id) if m is not None else None


def run_ingestion(session: Session, source: Source, *, reference: date, label: str = "mock") -> IngestionRun:
    run = IngestionRun(source=label, status="running")
    session.add(run)
    session.flush()

    found = created = 0
    errors: list[str] = []

    for rv in source.venues():
        found += 1
        try:
            upsert_venue(
                session,
                VenueInput(name=rv.name, lat=rv.lat, lng=rv.lng, address=rv.address, category=rv.category),
                SourceInfo(source_type=rv.source_type, source_url=rv.source_url, raw_payload=rv.raw_payload),
                derive_venue_signals(rv.source_type),
            )
            created += 1
        except Exception as exc:  # noqa: BLE001 — registra e segue
            errors.append(f"venue {rv.name!r}: {exc}")

    for page in source.event_pages():
        found += 1
        try:
            for ev in _extract_page(page, reference):
                if not ev.name:
                    continue
                venue = _resolve_venue(session, ev.venue_name)
                has_future = ev.starts_at is not None and ev.starts_at.date() >= reference
                signals = derive_event_signals(
                    source_type=page.source_type,
                    has_future_date=has_future,
                    venue_matched=venue is not None,
                )
                upsert_event(
                    session,
                    EventInput(
                        name=ev.name, starts_at=ev.starts_at,
                        venue_id=venue.id if venue is not None else None,
                        venue_name=ev.venue_name, ticket_url=ev.ticket_url,
                        raw_fields=ev.raw,
                    ),
                    SourceInfo(source_type=page.source_type, source_url=page.source_url, raw_payload=page.content),
                    signals,
                )
                created += 1
        except Exception as exc:  # noqa: BLE001 — registra e segue
            errors.append(f"page {page.source_url!r}: {exc}")

    run.status = "finished"
    run.records_found = found
    run.records_created = created
    run.finished_at = datetime.now(timezone.utc)
    run.errors = "\n".join(errors) or None
    session.flush()
    return run
