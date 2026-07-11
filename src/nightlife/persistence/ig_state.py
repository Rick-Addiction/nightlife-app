# src/nightlife/persistence/ig_state.py
"""Handles a varrer (uniao venue+organizer) e cursor de scraping por handle."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from ..domain.matching import haversine_km
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
                           has_contact=True,
                           business_status=v.business_status) == "relevant"
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


_SP_TZ = ZoneInfo("America/Sao_Paulo")
# cota da rodada reservada aos quentes (decisao do spec: 70/30). NB: com
# cap <= 3, ceil(cap*0.7) == cap — os frios so entram se faltar quente
# (nao reduza IG_MAX_PROFILES_PER_RUN abaixo de ~6 esperando rotacao fria).
_HOT_SHARE = 0.7


def _hot_handles(session: Session) -> set[str]:
    """Handles 'quentes': venue monitorado OU com evento futuro; organizer com
    evento futuro. 'Futuro' = a partir de hoje em America/Sao_Paulo."""
    today = datetime.now(_SP_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    hot: set[str] = set()
    future_venues = set(session.scalars(
        select(distinct(Event.venue_id)).where(
            Event.venue_id.is_not(None), Event.starts_at >= today)))
    for v in session.scalars(select(Venue).where(Venue.instagram.is_not(None))):
        if v.is_monitored or v.id in future_venues:
            hot.add(v.instagram)
    future_orgs = set(session.scalars(
        select(distinct(Event.organizer_id)).where(
            Event.organizer_id.is_not(None), Event.starts_at >= today)))
    for o in session.scalars(select(Organizer).where(Organizer.instagram.is_not(None))):
        if o.id in future_orgs:
            hot.add(o.instagram)
    return hot


def scrape_queue(session: Session, *, cap: int, pause_threshold: int = 3) -> list[str]:
    """Fila da rodada: nivel 1 (quentes) ate 70% do cap, resto completa com
    nivel 2; dentro de cada nivel, nunca-varrido primeiro e depois o mais
    antigo (mata a ordem alfabetica que so varria os primeiros do alfabeto)."""
    universe = handles_to_scrape(session, pause_threshold=pause_threshold)
    scraped_at = {st.handle: st.last_scraped_at
                  for st in session.scalars(select(IgProfileState))}
    epoch = datetime.min.replace(tzinfo=timezone.utc)

    def _staleness(h: str):
        ts = scraped_at.get(h)
        return (ts is not None, ts or epoch, h)

    hot_set = _hot_handles(session)
    hot = sorted((h for h in universe if h in hot_set), key=_staleness)
    cold = sorted((h for h in universe if h not in hot_set), key=_staleness)

    hot_slots = min(len(hot), math.ceil(cap * _HOT_SHARE))
    queue = hot[:hot_slots]
    queue += cold[: cap - len(queue)]
    if len(queue) < cap:                      # sobrou vaga (poucos frios):
        queue += hot[hot_slots:][: cap - len(queue)]  # quentes excedentes completam
    return queue


def record_venue_activity(session: Session, handle: str,
                          latest_post_at: "datetime | None") -> None:
    """Grava o sinal de vida do IG no(s) venue(s) donos do handle. Handle de
    organizer nao toca venue; None nao apaga valor existente."""
    if latest_post_at is None:
        return
    for v in session.scalars(select(Venue).where(Venue.instagram == handle)):
        v.ig_last_post_at = latest_post_at


def handles_in_area(session: Session, lat: float, lng: float, km: float,
                    *, pause_threshold: int = 3) -> list[str]:
    """Handles de VENUES dentro do raio, SEM cap (decisao do spec D-1: area
    varre tudo de uma vez). Nunca-varrido primeiro, depois o mais antigo.
    Exclui platform-handles, pausados e venues 'blocked' (buffet) — mas
    INCLUI dormants: em modo area o objetivo e descoberta (bar da Augusta
    com festa no IG e exatamente o que buscamos). Organizers ficam fora
    (nao tem geo)."""
    venues = session.scalars(select(Venue).where(
        Venue.instagram.is_not(None), Venue.lat.is_not(None), Venue.lng.is_not(None),
    )).all()
    with_events = set(session.scalars(
        select(Event.venue_id).where(Event.venue_id.is_not(None))).all())
    inside = {
        v.instagram for v in venues
        if haversine_km(lat, lng, v.lat, v.lng) <= km
        and not is_platform_handle(v.instagram)
        and venue_relevance(v.name, v.category, v.id in with_events, v.is_monitored,
                            has_contact=True,
                            business_status=v.business_status) != "blocked"
    }
    paused = set(session.scalars(
        select(IgProfileState.handle)
        .where(IgProfileState.consecutive_failures >= pause_threshold)).all())
    scraped_at = {st.handle: st.last_scraped_at
                  for st in session.scalars(select(IgProfileState))}
    epoch = datetime.min.replace(tzinfo=timezone.utc)

    def _staleness(h: str):
        ts = scraped_at.get(h)
        return (ts is not None, ts or epoch, h)

    return sorted(inside - paused, key=_staleness)
