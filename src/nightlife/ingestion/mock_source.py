# src/nightlife/ingestion/mock_source.py
from __future__ import annotations

import json
from pathlib import Path

from .base import RawEventPage, RawVenue


class MockSource:
    """Fonte de teste que serve registros a partir de listas em memoria ou de fixtures JSON."""

    def __init__(self, venues: list[RawVenue], event_pages: list[RawEventPage]) -> None:
        self._venues = venues
        self._pages = event_pages

    @classmethod
    def from_fixtures(cls, venues_path: Path | str, event_pages_path: Path | str) -> MockSource:
        venues = [RawVenue(**d) for d in json.loads(Path(venues_path).read_text(encoding="utf-8"))]
        pages = [RawEventPage(**d) for d in json.loads(Path(event_pages_path).read_text(encoding="utf-8"))]
        return cls(venues, pages)

    def venues(self) -> list[RawVenue]:
        return list(self._venues)

    def event_pages(self) -> list[RawEventPage]:
        return list(self._pages)
