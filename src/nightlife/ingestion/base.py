# src/nightlife/ingestion/base.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass
class RawVenue:
    name: str
    source_type: str
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    category: str | None = None
    source_url: str | None = None
    raw_payload: str = ""


@dataclass
class RawEventPage:
    kind: str          # "jsonld" | "html" | "freetext"
    content: str
    source_type: str
    source_url: str | None = None


class Source(Protocol):
    def venues(self) -> Iterable[RawVenue]: ...
    def event_pages(self) -> Iterable[RawEventPage]: ...
