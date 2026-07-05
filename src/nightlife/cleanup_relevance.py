# src/nightlife/cleanup_relevance.py
"""Limpa handles-lixo ja gravados (buffet + platform) e reporta eventos de buffet.
NAO-destrutivo: nao deleta venue nem evento; so zera instagram-lixo.
Uso: .venv/Scripts/python -m nightlife.cleanup_relevance
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .domain.nightlife_relevance import is_buffet_name, is_platform_handle
from .models import Event, Organizer, Venue


def cleanup(session: Session) -> tuple[int, int, int]:
    """Zera venue.instagram de buffet/plataforma e organizer.instagram de plataforma.
    Retorna (venues_limpos, organizers_limpos, eventos_em_venue_buffet)."""
    cleared_v = cleared_o = 0
    for v in session.scalars(select(Venue).where(Venue.instagram.is_not(None))).all():
        if is_buffet_name(v.name) or is_platform_handle(v.instagram):
            v.instagram = None
            cleared_v += 1
    for o in session.scalars(select(Organizer).where(Organizer.instagram.is_not(None))).all():
        if is_platform_handle(o.instagram):
            o.instagram = None
            cleared_o += 1
    buffet_ids = [v.id for v in session.scalars(select(Venue)).all() if is_buffet_name(v.name)]
    buffet_events = 0
    if buffet_ids:
        buffet_events = len(session.scalars(
            select(Event).where(Event.venue_id.in_(buffet_ids))
        ).all())
    return cleared_v, cleared_o, buffet_events


def main() -> None:
    with SessionLocal() as session:
        cv, co, be = cleanup(session)
        session.commit()
        print(f"handles-lixo zerados — venues: {cv} | organizers: {co}")
        print(f"eventos em venue-buffet (nao deletados; escondidos pela API): {be}")


if __name__ == "__main__":
    main()
