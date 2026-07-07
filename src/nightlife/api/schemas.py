# src/nightlife/api/schemas.py
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    category: str | None = None
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    instagram: str | None = None
    website: str | None = None
    status: str
    confidence: int
    effective_confidence: int = 0
    is_monitored: bool


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    venue_id: int | None = None
    status: str
    genre: str | None = None
    ticket_url: str | None = None
    confidence: int
    effective_confidence: int = 0
