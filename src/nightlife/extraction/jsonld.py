# src/nightlife/extraction/jsonld.py
from __future__ import annotations

import json

from bs4 import BeautifulSoup

from .base import ExtractedEvent, parse_iso


def _iter_jsonld(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = tag.get_text()
        if not text or not text.strip():
            continue
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            yield from data
        elif isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                yield from graph
            else:
                yield data


def _is_event(node) -> bool:
    if not isinstance(node, dict):
        return False
    t = node.get("@type")
    if isinstance(t, list):
        return any("Event" in str(x) for x in t)
    return isinstance(t, str) and "Event" in t


def _location_name(node):
    loc = node.get("location")
    if isinstance(loc, dict):
        return loc.get("name")
    if isinstance(loc, list) and loc and isinstance(loc[0], dict):
        return loc[0].get("name")
    if isinstance(loc, str):
        return loc
    return None


def _offers_url(node):
    off = node.get("offers")
    if isinstance(off, dict):
        return off.get("url")
    if isinstance(off, list) and off and isinstance(off[0], dict):
        return off[0].get("url")
    return None


def parse_jsonld_events(html: str, *, source_url: str | None = None) -> list[ExtractedEvent]:
    out: list[ExtractedEvent] = []
    for node in _iter_jsonld(html):
        if not _is_event(node):
            continue
        out.append(
            ExtractedEvent(
                name=node.get("name"),
                starts_at_raw=node.get("startDate"),
                starts_at=parse_iso(node.get("startDate")),
                ends_at_raw=node.get("endDate"),
                venue_name=_location_name(node),
                ticket_url=_offers_url(node),
                source_url=source_url,
                raw=node,
            )
        )
    return out
