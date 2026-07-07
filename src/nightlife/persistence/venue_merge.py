"""Fundir dois venues ja persistidos (survivor <- loser) e a passada de re-dedup
apos o geocoding. O upsert_venue so funde no momento da ingestao; aqui fundimos
duplicados que ja estao no banco e ganharam geo para confirmar o lugar fisico."""
from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..domain.matching import (
    VenueRef, classify_venue_match, geo_distance_km, match_venue,
)
from ..models import DedupeCandidate, Event, Venue, VenueSource
from .confidence import recompute_venue_confidence


def merge_venues(session: Session, survivor: Venue, loser: Venue, *, reference: date) -> Venue:
    # 1. evidencia do loser -> survivor, pulando (source_type, source_url) que o
    #    survivor ja tem (esses somem junto com o loser via cascade)
    existing = {
        (s.source_type, s.source_url)
        for s in session.scalars(select(VenueSource).where(VenueSource.venue_id == survivor.id))
    }
    for s in session.scalars(select(VenueSource).where(VenueSource.venue_id == loser.id)):
        if (s.source_type, s.source_url) not in existing:
            s.venue_id = survivor.id
            existing.add((s.source_type, s.source_url))

    # 2. eventos do loser -> survivor
    for e in session.scalars(select(Event).where(Event.venue_id == loser.id)):
        e.venue_id = survivor.id

    # 3. preenche lacunas do survivor a partir do loser
    if survivor.lat is None:
        survivor.lat, survivor.lng = loser.lat, loser.lng
    survivor.address = survivor.address or loser.address
    survivor.category = survivor.category or loser.category
    survivor.instagram = survivor.instagram or loser.instagram
    survivor.website = survivor.website or loser.website

    # 4. limpa DedupeCandidate que referenciam o loser (antes de apagar)
    for c in session.scalars(
        select(DedupeCandidate).where(
            or_(DedupeCandidate.a_id == loser.id, DedupeCandidate.b_id == loser.id)
        )
    ):
        session.delete(c)

    session.flush()
    session.delete(loser)          # cascade remove as VenueSource remanescentes do loser
    session.flush()
    recompute_venue_confidence(session, survivor, reference=reference)
    return survivor
