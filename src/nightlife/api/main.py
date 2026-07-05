# src/nightlife/api/main.py
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.freshness import freshness_factor
from ..domain.nightlife_relevance import is_buffet_name, venue_relevance
from ..models import Event, Venue
from .deps import get_session
from .schemas import EventOut, VenueOut

app = FastAPI(title="Nightlife SP — API")


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        min_lng, min_lat, max_lng, max_lat = (float(x) for x in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bbox deve ser 'minLng,minLat,maxLng,maxLat'") from exc
    return min_lng, min_lat, max_lng, max_lat


def _with_effective(out_cls, entity, now: datetime):
    out = out_cls.model_validate(entity)
    out.effective_confidence = round(entity.confidence * freshness_factor(entity.last_seen_at, now))
    return out


@app.get("/venues", response_model=list[VenueOut])
def list_venues(
    type: str | None = None,
    bbox: str | None = None,
    min_confidence: int = 0,
    include_all: bool = False,
    session: Session = Depends(get_session),
):
    # pre-filtro no SQL pelo score armazenado e valido: effective <= stored
    q = select(Venue).where(Venue.confidence >= min_confidence)
    if type is not None:
        q = q.where(Venue.category == type)
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = _parse_bbox(bbox)
        q = q.where(
            Venue.lat >= min_lat, Venue.lat <= max_lat,
            Venue.lng >= min_lng, Venue.lng <= max_lng,
        )
    venues = session.scalars(q).all()
    if not include_all:
        with_events = set(session.scalars(
            select(Event.venue_id).where(Event.venue_id.is_not(None))
        ).all())
        venues = [
            v for v in venues
            if venue_relevance(v.name, v.category, v.id in with_events, v.is_monitored) == "relevant"
        ]
    now = datetime.now(timezone.utc)
    outs = [_with_effective(VenueOut, v, now) for v in venues]
    outs = [o for o in outs if o.effective_confidence >= min_confidence]
    outs.sort(key=lambda o: o.effective_confidence, reverse=True)
    return outs


@app.get("/venues/{venue_id}", response_model=VenueOut)
def get_venue(venue_id: int, session: Session = Depends(get_session)):
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue nao encontrado")
    return _with_effective(VenueOut, venue, datetime.now(timezone.utc))


@app.get("/events", response_model=list[EventOut])
def list_events(
    date_from: date | None = None,
    date_to: date | None = None,
    bbox: str | None = None,
    genre: str | None = None,
    min_confidence: int = 0,
    include_past: bool = False,
    include_all: bool = False,
    session: Session = Depends(get_session),
):
    if date_from is None and not include_past:
        # default: so eventos futuros — a lista nao acumula passado eternamente
        date_from = date.today()
    q = select(Event).where(Event.confidence >= min_confidence)
    if date_from is not None:
        q = q.where(Event.starts_at >= date_from)
    if date_to is not None:
        q = q.where(Event.starts_at <= date_to)
    if genre is not None:
        q = q.where(Event.genre == genre)
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = _parse_bbox(bbox)
        q = q.join(Venue, Event.venue_id == Venue.id).where(
            Venue.lat >= min_lat, Venue.lat <= max_lat,
            Venue.lng >= min_lng, Venue.lng <= max_lng,
        )
    now = datetime.now(timezone.utc)
    outs = [_with_effective(EventOut, e, now)
            for e in session.scalars(q.order_by(Event.starts_at)).all()]
    outs = [o for o in outs if o.effective_confidence >= min_confidence]
    if not include_all:
        blocked_ids = {v.id for v in session.scalars(select(Venue)).all() if is_buffet_name(v.name)}
        outs = [o for o in outs if o.venue_id not in blocked_ids]
    return outs


@app.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="evento nao encontrado")
    return _with_effective(EventOut, event, datetime.now(timezone.utc))
