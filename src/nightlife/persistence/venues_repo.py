# src/nightlife/persistence/venues_repo.py
from __future__ import annotations

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.matching import VenueRef, match_venue
from ..domain.scoring import VenueSignals, score_venue
from ..models import Venue, VenueSource
from .inputs import SourceInfo, VenueInput


def _hash(payload: str) -> str:
    return hashlib.sha256((payload or "").encode("utf-8")).hexdigest()


def upsert_venue(
    session: Session, candidate: VenueInput, source: SourceInfo, signals: VenueSignals
) -> Venue:
    existing = session.scalars(select(Venue)).all()
    refs = [VenueRef(v.id, v.name, v.address, v.lat, v.lng) for v in existing]
    match = match_venue(
        VenueRef(None, candidate.name, candidate.address, candidate.lat, candidate.lng), refs
    )

    if match is not None:
        venue = session.get(Venue, match.venue.id)
        venue.last_seen_at = func.now()
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

    venue.confidence = score_venue(signals)
    session.add(VenueSource(
        venue_id=venue.id,
        source_type=source.source_type,
        source_url=source.source_url,
        raw_payload_hash=_hash(source.raw_payload),
        extracted_fields=source.extracted_fields,
        confidence_contribution=venue.confidence,
    ))
    return venue
