# src/nightlife/persistence/ig_state.py
"""Handles a varrer (uniao venue+organizer) e cursor de scraping por handle."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import IgProfileState, Organizer, Venue


def handles_to_scrape(session: Session, *, pause_threshold: int = 3) -> list[str]:
    """Uniao distinta e ordenada de venue.instagram e organizer.instagram,
    menos os handles pausados (falhas consecutivas >= pause_threshold)."""
    vs = session.scalars(select(Venue.instagram).where(Venue.instagram.is_not(None))).all()
    os_ = session.scalars(select(Organizer.instagram).where(Organizer.instagram.is_not(None))).all()
    paused = set(session.scalars(
        select(IgProfileState.handle).where(IgProfileState.consecutive_failures >= pause_threshold)
    ).all())
    return sorted({*vs, *os_} - paused)


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
