# src/nightlife/persistence/venues_repo.py
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.matching import VenueRef, classify_venue_match, match_venue
from ..models import DedupeCandidate, Venue
from .confidence import VENUE_SOURCE_CONTRIBUTION, recompute_venue_confidence
from .evidence import record_venue_evidence
from .inputs import SourceInfo, VenueInput


def upsert_venue(
    session: Session, candidate: VenueInput, source: SourceInfo, *, reference: date
) -> Venue:
    existing = session.scalars(select(Venue)).all()
    refs = [VenueRef(v.id, v.name, v.address, v.lat, v.lng) for v in existing]
    # threshold=0.0: queremos o melhor match SEMPRE; a decisao vem das faixas
    best = match_venue(
        VenueRef(None, candidate.name, candidate.address, candidate.lat, candidate.lng),
        refs, threshold=0.0,
    )
    decision = classify_venue_match(best.score) if best is not None else "distinct"

    if decision == "auto_merge":
        venue = session.get(Venue, best.venue.id)
        venue.last_seen_at = datetime.now(timezone.utc)
        # preenche lacunas sem sobrescrever dados ja existentes
        venue.lat = venue.lat if venue.lat is not None else candidate.lat
        venue.lng = venue.lng if venue.lng is not None else candidate.lng
        venue.address = venue.address or candidate.address
        venue.category = venue.category or candidate.category
    else:
        venue = Venue(
            name=candidate.name, lat=candidate.lat, lng=candidate.lng,
            address=candidate.address, category=candidate.category, status="unverified",
        )
        session.add(venue)
        session.flush()
        if decision == "review":
            session.add(DedupeCandidate(
                kind="venue", a_id=venue.id, b_id=best.venue.id,
                similarity_score=best.score, decision="review",
            ))

    record_venue_evidence(
        session, venue.id, source,
        contribution=VENUE_SOURCE_CONTRIBUTION.get(source.source_type, 0),
    )
    recompute_venue_confidence(session, venue, reference=reference)
    return venue
