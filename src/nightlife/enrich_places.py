"""Enriquecimento de venues via Place Details + reconciliacao (Ciclo A).

Details por place_id: nome canonico pt-BR (renomeia com trilha), businessStatus
(mata fechados), websiteUri (site oficial -> elo do Ciclo B). Cache de 30 dias
via enriched_at. Sob demanda: python -m nightlife.enrich_places
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import distinct, or_, select
from sqlalchemy.orm import Session

from .domain.matching import _haversine_km, name_similarity
from .models import DedupeCandidate, Event, Venue, VenueSource, VerificationLog
from .persistence.venue_merge import _pick_survivor, merge_venues

_STATUS_MAP = {
    "OPERATIONAL": "operational",
    "CLOSED_TEMPORARILY": "closed",
    "CLOSED_PERMANENTLY": "permanently_closed",
}


def _place_ids_by_venue(session: Session) -> dict[int, str]:
    """place_id (source_url) mais recente por venue com evidencia google_places."""
    rows = session.execute(
        select(VenueSource.venue_id, VenueSource.source_url)
        .where(VenueSource.source_type == "google_places",
               VenueSource.source_url.is_not(None))
        .order_by(VenueSource.venue_id, VenueSource.last_seen_at.desc())
    ).all()
    out: dict[int, str] = {}
    for vid, url in rows:
        out.setdefault(vid, url)    # primeiro = last_seen mais recente
    return out


def enrich_all(session: Session, client, *, now: datetime, max_age_days: int = 30) -> dict:
    out = {"enriched": 0, "renamed": 0, "websites_set": 0, "closed_perm": 0,
           "closed_temp": 0, "skipped_cached": 0, "errors": 0}
    cutoff = now - timedelta(days=max_age_days)
    for vid, pid in _place_ids_by_venue(session).items():
        venue = session.get(Venue, vid)
        if venue is None:
            continue
        if venue.enriched_at is not None and venue.enriched_at >= cutoff:
            out["skipped_cached"] += 1
            continue
        det = client.place_details(pid)
        if det is None:
            out["errors"] += 1      # retentavel: NAO grava enriched_at
            continue
        if det.name and det.name != venue.name:
            session.add(VerificationLog(
                entity_type="venue", entity_id=venue.id,
                note=f"rename: {venue.name!r} -> {det.name!r} (places)"))
            venue.name = det.name
            out["renamed"] += 1
        if det.website and det.website != venue.website:
            venue.website = det.website
            out["websites_set"] += 1
        venue.business_status = det.business_status
        mapped = _STATUS_MAP.get(det.business_status or "")
        if mapped:
            venue.status = mapped
        if det.business_status == "CLOSED_PERMANENTLY":
            out["closed_perm"] += 1
        elif det.business_status == "CLOSED_TEMPORARILY":
            out["closed_temp"] += 1
        venue.enriched_at = now
        out["enriched"] += 1
    session.flush()
    return out


def _sources_by_venue(session: Session) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for vid, stype in session.execute(select(VenueSource.venue_id, VenueSource.source_type)):
        out.setdefault(vid, set()).add(stype)
    return out


def reconcile_venues(session: Session, *, reference: date) -> dict:
    """Duas regras, nesta ordem. 1) Consolidacao: par <=30m com score >=0.70
    (name_similarity + boost geo 0.1, semantica do match_venue) e >=1 lado
    verificado -> merge (mata pins duplicados tipo 'Kat Klub' vs 'Kat Klub Sao
    Paulo'). 2) Supersessao: fantasma (1 fonte ra/osm, 0 eventos) com exatamente
    1 verificado <=30m -> funde nele (Inferno->Selva, Beco->Kat Klub);
    ambiguidade -> fila de review. Merges via merge_venues (auditavel)."""
    out = {"consolidated": 0, "superseded": 0, "review_queued": 0, "untouched": 0}

    def _snapshot():
        srcs = _sources_by_venue(session)
        with_ev = set(session.scalars(
            select(distinct(Event.venue_id)).where(Event.venue_id.is_not(None))))
        venues = session.scalars(select(Venue).where(Venue.lat.is_not(None))).all()
        return venues, srcs, with_ev

    def _verified(v: Venue, srcs: dict[int, set[str]]) -> bool:
        return ("google_places" in srcs.get(v.id, set())
                and v.business_status != "CLOSED_PERMANENTLY")

    def _dist_km(a: Venue, b: Venue) -> float:
        return _haversine_km(a.lat, a.lng, b.lat, b.lng)

    # regra 1: consolidacao por nome
    venues, srcs, _ = _snapshot()
    gone: set[int] = set()
    for i, a in enumerate(venues):
        if a.id in gone:
            continue
        for b in venues[i + 1:]:
            if b.id in gone or a.id in gone:
                continue
            if not (_verified(a, srcs) or _verified(b, srcs)):
                continue
            if _dist_km(a, b) > 0.03:
                continue
            # score com o MESMO boost geo do match_venue (par <=30m): sem ele,
            # "Kat Klub Sao Paulo" vs "Kat Klub" da 0.615 cru e nao consolidaria
            if min(1.0, name_similarity(a.name, b.name) + 0.1) < 0.70:
                continue
            survivor, loser = _pick_survivor(a, b)
            merge_venues(session, survivor, loser, reference=reference)
            gone.add(loser.id)
            out["consolidated"] += 1

    # regra 2: supersessao de fantasmas (snapshot fresco: regra 1 mudou o banco)
    venues, srcs, with_ev = _snapshot()
    gone = set()
    for g in venues:
        if g.id in gone:
            continue
        gsrc = srcs.get(g.id, set())
        if not (len(gsrc) == 1 and next(iter(gsrc)) in ("ra", "osm")):
            continue
        if g.id in with_ev:
            continue                      # tem evento: nao e fantasma
        near30 = [v for v in venues
                  if v.id != g.id and v.id not in gone
                  and _verified(v, srcs) and _dist_km(g, v) <= 0.03]
        if len(near30) == 1:
            merge_venues(session, near30[0], g, reference=reference)
            gone.add(g.id)
            out["superseded"] += 1
            continue
        near60 = [v for v in venues
                  if v.id != g.id and v.id not in gone
                  and _verified(v, srcs) and _dist_km(g, v) <= 0.06]
        if len(near30) >= 2 or near60:
            other = (near30 or near60)[0]
            exists = session.scalars(select(DedupeCandidate).where(
                DedupeCandidate.kind == "venue",
                or_((DedupeCandidate.a_id == g.id) & (DedupeCandidate.b_id == other.id),
                    (DedupeCandidate.a_id == other.id) & (DedupeCandidate.b_id == g.id)),
            )).first()
            if exists is None:
                session.add(DedupeCandidate(
                    kind="venue", a_id=g.id, b_id=other.id,
                    similarity_score=name_similarity(g.name, other.name),
                    decision="review"))
            out["review_queued"] += 1
        else:
            out["untouched"] += 1

    session.flush()
    return out


def main() -> None:
    from .config import GOOGLE_MAPS_API_KEY

    if not GOOGLE_MAPS_API_KEY:
        print("ERRO: defina GOOGLE_MAPS_API_KEY (Places API New + billing)")
        sys.exit(1)

    import truststore
    truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

    from .db import SessionLocal
    from .ingestion.places_client import PlacesClient

    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        client = PlacesClient(GOOGLE_MAPS_API_KEY)
        out = enrich_all(session, client, now=now)
        rec = reconcile_venues(session, reference=now.date())
        session.commit()
        print("enrich:", out)
        print("reconcile:", rec)


if __name__ == "__main__":
    main()
