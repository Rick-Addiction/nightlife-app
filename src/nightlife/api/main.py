# src/nightlife/api/main.py
from __future__ import annotations

from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

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


@app.get("/venues", response_model=list[VenueOut])
def list_venues(
    type: str | None = None,
    bbox: str | None = None,
    min_confidence: int = 0,
    session: Session = Depends(get_session),
):
    q = select(Venue).where(Venue.confidence >= min_confidence)
    if type is not None:
        q = q.where(Venue.category == type)
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = _parse_bbox(bbox)
        q = q.where(
            Venue.lat >= min_lat, Venue.lat <= max_lat,
            Venue.lng >= min_lng, Venue.lng <= max_lng,
        )
    return session.scalars(q.order_by(Venue.confidence.desc())).all()


@app.get("/venues/{venue_id}", response_model=VenueOut)
def get_venue(venue_id: int, session: Session = Depends(get_session)):
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue nao encontrado")
    return venue


@app.get("/events", response_model=list[EventOut])
def list_events(
    date_from: date | None = None,
    date_to: date | None = None,
    bbox: str | None = None,
    genre: str | None = None,
    min_confidence: int = 0,
    session: Session = Depends(get_session),
):
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
    return session.scalars(q.order_by(Event.starts_at)).all()


@app.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="evento nao encontrado")
    return event
