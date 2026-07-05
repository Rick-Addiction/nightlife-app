# src/nightlife/models.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Venue(Base):
    __tablename__ = "venues"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(50), default=None)
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lng: Mapped[float | None] = mapped_column(Float, default=None)
    address: Mapped[str | None] = mapped_column(String(500), default=None)
    instagram: Mapped[str | None] = mapped_column(String(200), default=None)
    website: Mapped[str | None] = mapped_column(String(500), default=None)
    status: Mapped[str] = mapped_column(String(30), default="unverified")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    is_monitored: Mapped[bool] = mapped_column(default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sources: Mapped[list["VenueSource"]] = relationship(
        back_populates="venue", cascade="all, delete-orphan"
    )
    events: Mapped[list["Event"]] = relationship(back_populates="venue")


class VenueSource(Base):
    __tablename__ = "venue_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_payload_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    extracted_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_contribution: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    venue: Mapped["Venue"] = relationship(back_populates="sources")


class Organizer(Base):
    __tablename__ = "organizers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    instagram: Mapped[str | None] = mapped_column(String(200), default=None)
    website: Mapped[str | None] = mapped_column(String(500), default=None)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(400))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), default=None)
    organizer_id: Mapped[int | None] = mapped_column(ForeignKey("organizers.id"), default=None)
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    lineup_text: Mapped[str | None] = mapped_column(Text, default=None)
    genre: Mapped[str | None] = mapped_column(String(80), default=None)
    ticket_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    raw_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    venue: Mapped["Venue | None"] = relationship(back_populates="events")
    organizer: Mapped["Organizer | None"] = relationship()
    sources: Mapped[list["EventSource"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventSource(Base):
    __tablename__ = "event_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_payload_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    extracted_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_contribution: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event: Mapped["Event"] = relationship(back_populates="sources")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(60))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    status: Mapped[str] = mapped_column(String(30), default="running")
    records_found: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[str | None] = mapped_column(Text, default=None)


class DedupeCandidate(Base):
    __tablename__ = "dedupe_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # "event" | "venue"
    a_id: Mapped[int] = mapped_column(Integer)
    b_id: Mapped[int] = mapped_column(Integer)
    similarity_score: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(20))  # "auto_merge" | "review" | "distinct"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VerificationLog(Base):
    __tablename__ = "verification_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20))  # "venue" | "event"
    entity_id: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IgProfileState(Base):
    __tablename__ = "ig_profile_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    handle: Mapped[str] = mapped_column(String(200), unique=True)
    last_shortcode: Mapped[str | None] = mapped_column(String(50), default=None)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
