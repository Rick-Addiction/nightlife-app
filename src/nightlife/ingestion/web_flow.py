# src/nightlife/ingestion/web_flow.py
"""Orquestra a extracao do site de um venue (Ciclo E-2a): fetch -> JSON-LD ou
codex-texto -> acoes ancoradas por venue_id. Cache por hash: site parado pula."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..extraction.jsonld import parse_jsonld_events
from ..extraction.post_actions import AddEvent, PostInterpretation, sanitize_actions
from ..models import Event, Venue
from ..persistence.action_executor import execute_actions
from .post_interpreter import Document, VenueContext
from .web_source import agenda_links, looks_empty, visible_text

_SP_TODAY_CAP = 20
_TEXT_CAP = 12000        # trunca texto longo pro prompt (custo/alucinacao)


def jsonld_to_actions(html: str, *, source_url: str | None) -> list[AddEvent]:
    out: list[AddEvent] = []
    for ev in parse_jsonld_events(html, source_url=source_url):
        if not ev.name or not ev.starts_at_raw:
            continue
        out.append(AddEvent(
            name=ev.name, starts_at_iso=ev.starts_at_raw, ticket_url=ev.ticket_url,
            quotes={"name": ev.name}, confidence={"name": 1.0}))
    return out


def _context_for(session: Session, venue: Venue, today: date) -> VenueContext:
    now = datetime.now(timezone.utc)
    known: list[tuple[str, str | None]] = []
    for e in session.scalars(
            select(Event).where(Event.venue_id == venue.id, Event.status != "cancelled")
            .order_by(Event.starts_at.asc().nullslast()).limit(_SP_TODAY_CAP)):
        if e.starts_at is None or e.starts_at >= now:
            known.append((e.name, e.starts_at.date().isoformat() if e.starts_at else None))
    return VenueContext(venue_name=venue.name, handle=venue.instagram,
                        today_iso=today.isoformat(), known_events=known)


def crawl_venue(session: Session, venue: Venue, *, fetcher: Callable[[str], str],
                interpreter, reference: date) -> dict:
    stats = {"venue": venue.name, "add": 0, "jsonld": 0, "codex": 0, "skipped": False}
    if not venue.website:
        return stats
    home = fetcher(venue.website)
    digest = hashlib.sha256((home or "").encode("utf-8", "replace")).hexdigest()
    if venue.web_last_hash == digest:
        stats["skipped"] = True
        return stats

    pages = [(venue.website, home)]
    for link in agenda_links(home, base_url=venue.website):
        pages.append((link, fetcher(link)))

    ctx = _context_for(session, venue, reference)
    for url, html in pages:
        if not html:
            continue
        acts = jsonld_to_actions(html, source_url=url)
        if acts:
            stats["jsonld"] += len(acts)
            interp = PostInterpretation(actions=acts)
        else:
            doc = Document(kind="web_page", image_path=None, caption=None, handle=None,
                           permalink=url, text=visible_text(html)[:_TEXT_CAP], venue_id=venue.id)
            result = interpreter.interpret(doc, ctx)
            if result is None:
                continue
            stats["codex"] += 1
            interp = result
        doc = Document(kind="web_page", image_path=None, caption=None, handle=None,
                       permalink=url, text=None, venue_id=venue.id)
        s = execute_actions(session, doc, sanitize_actions(interp), reference=reference)
        stats["add"] += s["add"]

    venue.web_last_hash = digest
    venue.web_checked_at = datetime.now(timezone.utc)
    session.commit()
    return stats
