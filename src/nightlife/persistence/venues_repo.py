# src/nightlife/persistence/venues_repo.py
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.matching import VenueRef, classify_venue_match, geo_distance_km, match_venue
from ..models import DedupeCandidate, Venue, VenueSource
from .confidence import VENUE_SOURCE_CONTRIBUTION, recompute_venue_confidence
from .evidence import record_venue_evidence
from .inputs import SourceInfo, VenueInput


def _fill_and_record(session: Session, venue: Venue, candidate: VenueInput,
                     source: SourceInfo, reference: date) -> Venue:
    """Reusa um venue existente: preenche lacunas, grava evidencia (idempotente),
    recomputa confianca."""
    venue.last_seen_at = datetime.now(timezone.utc)
    venue.lat = venue.lat if venue.lat is not None else candidate.lat
    venue.lng = venue.lng if venue.lng is not None else candidate.lng
    venue.address = venue.address or candidate.address
    venue.category = venue.category or candidate.category
    record_venue_evidence(
        session, venue.id, source,
        contribution=VENUE_SOURCE_CONTRIBUTION.get(source.source_type, 0),
    )
    recompute_venue_confidence(session, venue, reference=reference)
    return venue


def upsert_venue(
    session: Session, candidate: VenueInput, source: SourceInfo, *, reference: date
) -> Venue:
    # identidade por source_url: mesmo (source_type, source_url) = MESMA venue,
    # idempotente e independente de geo (senao venue sem geo duplicaria a cada run).
    if source.source_url:
        known = session.scalars(
            select(Venue).join(VenueSource).where(
                VenueSource.source_type == source.source_type,
                VenueSource.source_url == source.source_url,
            )
        ).first()
        if known is not None:
            return _fill_and_record(session, known, candidate, source, reference)

    existing = session.scalars(select(Venue)).all()
    refs = [VenueRef(v.id, v.name, v.address, v.lat, v.lng) for v in existing]
    cand_ref = VenueRef(None, candidate.name, candidate.address, candidate.lat, candidate.lng)
    # threshold=0.0: queremos o melhor match SEMPRE; a decisao vem das faixas
    best = match_venue(cand_ref, refs, threshold=0.0)
    decision = "distinct"
    if best is not None:
        decision = classify_venue_match(
            best.score, distance_km=geo_distance_km(cand_ref, best.venue)
        )

    if decision == "auto_merge":
        return _fill_and_record(session, session.get(Venue, best.venue.id), candidate, source, reference)

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
