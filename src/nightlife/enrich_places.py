"""Enriquecimento de venues via Place Details + reconciliacao (Ciclo A).

Details por place_id: nome canonico pt-BR (renomeia com trilha), businessStatus
(mata fechados), websiteUri (site oficial -> elo do Ciclo B). Cache de 30 dias
via enriched_at. Sob demanda: python -m nightlife.enrich_places
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Venue, VenueSource, VerificationLog

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
        session.commit()
        print("enrich:", out)


if __name__ == "__main__":
    main()
