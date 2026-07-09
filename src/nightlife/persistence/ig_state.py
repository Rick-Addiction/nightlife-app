# src/nightlife/persistence/ig_state.py
"""Handles a varrer (uniao venue+organizer) e cursor de scraping por handle."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.nightlife_relevance import is_platform_handle, venue_relevance
from ..models import Event, IgProfileState, Organizer, Venue


def handles_to_scrape(session: Session, *, pause_threshold: int = 3) -> list[str]:
    """Handles a varrer: handles de venues RELEVANT (com-evento/monitorado, ou
    nightclub vivo — aqui sempre com_contact=True pois todas tem instagram)
    uniao com os de organizers, menos platform-handles e menos os pausados."""
    venues = session.scalars(select(Venue).where(Venue.instagram.is_not(None))).all()
    with_events = set(session.scalars(
        select(Event.venue_id).where(Event.venue_id.is_not(None))
    ).all())
    vhandles = {
        v.instagram for v in venues
        if venue_relevance(v.name, v.category, v.id in with_events, v.is_monitored,
                           has_contact=True) == "relevant"
    }
    ohandles = set(session.scalars(
        select(Organizer.instagram).where(Organizer.instagram.is_not(None))
    ).all())
    handles = {h for h in (vhandles | ohandles) if h and not is_platform_handle(h)}
    paused = set(session.scalars(
        select(IgProfileState.handle).where(IgProfileState.consecutive_failures >= pause_threshold)
    ).all())
    return sorted(handles - paused)


def get_or_create_state(session: Session, handle: str) -> IgProfileState:
    st = session.scalars(
        select(IgProfileState).where(IgProfileState.handle == handle)
    ).first()
    if st is None:
        st = IgProfileState(handle=handle)
        session.add(st)
        session.flush()
    return st


def record_success(state: IgProfileState, last_shortcode: str | None) -> None:
    state.consecutive_failures = 0
    state.last_scraped_at = datetime.now(timezone.utc)
    if last_shortcode:
        state.last_shortcode = last_shortcode


def record_failure(state: IgProfileState) -> None:
    state.consecutive_failures += 1
    state.last_scraped_at = datetime.now(timezone.utc)
