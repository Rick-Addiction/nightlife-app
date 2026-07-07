# src/nightlife/repair_ra_dedup.py
"""Repara os merges falsos geoless do RA: apaga SO os dados source_type='ra'
(re-derivaveis), deixando OSM/Sympla/flyer intactos. Depois rode ingest_ra p/
re-criar os venues do RA ja com o dedup endurecido (separados, sem colapso).

Uso: .venv/Scripts/python -m nightlife.repair_ra_dedup  (depois: -m nightlife.ingest_ra)
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import DedupeCandidate, Event, EventSource, Venue, VenueSource


def repair(session: Session) -> dict:
    """Apaga evidencia/venues/eventos que sao SO do RA. Retorna contagens.
    Ordem FK-safe: evidencia de evento RA -> eventos orfaos -> evidencia de venue
    RA -> venues orfaos (sem fonte e sem evento) -> candidatos de dedupe."""
    ev_srcs = session.scalars(select(EventSource).where(EventSource.source_type == "ra")).all()
    for s in ev_srcs:
        session.delete(s)
    session.flush()

    orphan_events = session.scalars(select(Event).where(~Event.sources.any())).all()
    for e in orphan_events:
        session.delete(e)
    session.flush()

    v_srcs = session.scalars(select(VenueSource).where(VenueSource.source_type == "ra")).all()
    for s in v_srcs:
        session.delete(s)
    session.flush()

    orphan_venues = session.scalars(
        select(Venue).where(~Venue.sources.any(), ~Venue.events.any())
    ).all()
    for v in orphan_venues:
        session.delete(v)
    session.flush()

    cands = session.scalars(select(DedupeCandidate)).all()
    for c in cands:
        session.delete(c)
    session.flush()

    return {"event_sources_ra": len(ev_srcs), "eventos_orfaos": len(orphan_events),
            "venue_sources_ra": len(v_srcs), "venues_orfaos": len(orphan_venues),
            "dedupe_candidates": len(cands)}


def main() -> None:
    with SessionLocal() as session:
        counts = repair(session)
        session.commit()
        print("repair RA:", counts)
        print("agora rode: .venv/Scripts/python -m nightlife.ingest_ra")


if __name__ == "__main__":
    main()
