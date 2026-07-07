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
from ..models import DedupeCandidate, Event, Venue, VenueSource, VerificationLog
from .confidence import recompute_venue_confidence


def merge_venues(session: Session, survivor: Venue, loser: Venue, *, reference: date) -> Venue:
    # merge e irreversivel (delete fisico): registra a trilha antes de qualquer
    # coisa, enquanto loser.id/name ainda sao validos.
    session.add(VerificationLog(
        entity_type="venue", entity_id=survivor.id,
        note=f"merge: venue {loser.id} ({loser.name!r}) -> survivor {survivor.id} ({survivor.name!r})",
    ))
    # 1. evidencia do loser -> survivor, pulando (source_type, source_url) que o
    #    survivor ja tem (esses somem junto com o loser via cascade). NB: iteramos
    #    via query (nao via loser.sources) de proposito — carregar a colecao do
    #    loser faria o cascade delete-orphan varrer linhas ja remapeadas no flush.
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


def _ref(v: Venue) -> VenueRef:
    return VenueRef(v.id, v.name, v.address, v.lat, v.lng)


def _pick_survivor(a: Venue, b: Venue) -> tuple[Venue, Venue]:
    """survivor = maior confianca; empate -> menor id (mais antigo, tende a OSM)."""
    if (a.confidence, -a.id) >= (b.confidence, -b.id):
        return a, b
    return b, a


def rededup_geocoded(session: Session, geocoded_ids: list[int], *, reference: date) -> dict:
    """Re-avalia cada venue recem-geocodado contra os outros COM geo. auto_merge
    funde; review enfileira DedupeCandidate; distinct ignora."""
    counts = {"merged": 0, "review": 0, "distinct": 0}
    merged_away: set[int] = set()

    for vid in geocoded_ids:
        if vid in merged_away:
            continue
        venue = session.get(Venue, vid)
        if venue is None or venue.lat is None:
            continue

        others = session.scalars(
            select(Venue).where(Venue.id != vid, Venue.lat.is_not(None))
        ).all()
        if not others:
            continue
        best = match_venue(_ref(venue), [_ref(o) for o in others], threshold=0.0)
        if best is None:
            continue
        other = session.get(Venue, best.venue.id)
        decision = classify_venue_match(
            best.score, distance_km=geo_distance_km(_ref(venue), _ref(other))
        )

        if decision == "auto_merge":
            survivor, loser = _pick_survivor(venue, other)
            merge_venues(session, survivor, loser, reference=reference)
            merged_away.add(loser.id)
            counts["merged"] += 1
        elif decision == "review":
            exists = session.scalars(
                select(DedupeCandidate).where(
                    DedupeCandidate.kind == "venue",
                    or_(
                        (DedupeCandidate.a_id == venue.id) & (DedupeCandidate.b_id == other.id),
                        (DedupeCandidate.a_id == other.id) & (DedupeCandidate.b_id == venue.id),
                    ),
                )
            ).first()
            if exists is None:
                session.add(DedupeCandidate(
                    kind="venue", a_id=venue.id, b_id=other.id,
                    similarity_score=best.score, decision="review",
                ))
            counts["review"] += 1
        else:
            counts["distinct"] += 1

    session.flush()
    return counts
