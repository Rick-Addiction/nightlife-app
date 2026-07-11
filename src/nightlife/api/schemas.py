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
    ig_last_post_at: datetime | None = None
    places_verified: bool = False


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
    flyer_url: str | None = None
    confidence: int
    effective_confidence: int = 0


class AreaSweepIn(BaseModel):
    lat: float
    lng: float
    km: float = 2.0


class AreaSweepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    label: str | None = None
    status: str
    phase: str
    total_handles: int
    done_handles: int = 0
    report: list = []
    diff: dict | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
