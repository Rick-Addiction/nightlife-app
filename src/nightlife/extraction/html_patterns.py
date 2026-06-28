# src/nightlife/extraction/html_patterns.py
from __future__ import annotations

from bs4 import BeautifulSoup

from .base import ExtractedEvent


def _has_event_type(value) -> bool:
    return bool(value) and "Event" in value


def parse_html_patterns(html: str, *, source_url: str | None = None) -> list[ExtractedEvent]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[ExtractedEvent] = []
    for node in soup.find_all(attrs={"itemtype": _has_event_type}):
        name_el = node.find(attrs={"itemprop": "name"})
        start_el = node.find(attrs={"itemprop": "startDate"})
        starts_raw = None
        if start_el is not None:
            starts_raw = start_el.get("content") or start_el.get_text(strip=True)
        out.append(
            ExtractedEvent(
                name=name_el.get_text(strip=True) if name_el else None,
                starts_at_raw=starts_raw,
                source_url=source_url,
            )
        )
    return out
