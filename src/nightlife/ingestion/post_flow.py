# src/nightlife/ingestion/post_flow.py
"""Orquestra o inbox de posts (spec E-1 §3.4): dHash dedupe -> Document ->
interprete -> saneamento -> executor. processed/failed sao movidos pelo
CALLER (padrao do FlyerSource). IngestionRun label='posts'."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..extraction.imagehash import dhash
from ..extraction.post_actions import sanitize_actions
from ..models import Event, IngestionRun, Venue
from .post_interpreter import Document, PostInterpreter, VenueContext

_log = logging.getLogger(__name__)
_IMAGE_GLOBS = ("*.jpg", "*.jpeg", "*.png", "*.webp")
_SP_TZ = ZoneInfo("America/Sao_Paulo")
_KNOWN_CAP = 20


@dataclass
class FlowStats:
    processed_paths: list[Path] = field(default_factory=list)
    failed_paths: list[Path] = field(default_factory=list)
    stats_by_handle: dict[str, dict] = field(default_factory=dict)
    created: int = 0


def _context_for(session: Session, handle: str | None, today: date) -> VenueContext:
    venue = None
    if handle:
        venue = session.scalars(
            select(Venue).where(Venue.instagram == handle)
            .order_by(Venue.confidence.desc(), Venue.id)).first()
    known: list[tuple[str, str | None]] = []
    if venue is not None:
        now = datetime.now(timezone.utc)
        for e in session.scalars(
                select(Event).where(Event.venue_id == venue.id,
                                    Event.status != "cancelled")
                .order_by(Event.starts_at.asc().nullslast()).limit(_KNOWN_CAP)):
            if e.starts_at is None or e.starts_at >= now:
                known.append((e.name, e.starts_at.date().isoformat() if e.starts_at else None))
    return VenueContext(venue_name=venue.name if venue else None, handle=handle,
                        today_iso=today.isoformat(), known_events=known)


def _merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if k == "ignore":
            ig = dst.setdefault("ignore", {})
            for r, n in v.items():
                ig[r] = ig.get(r, 0) + n
        else:
            dst[k] = dst.get(k, 0) + v


def process_inbox(session: Session, inbox: Path, interpreter: PostInterpreter,
                  *, reference: date, log=print) -> FlowStats:
    from ..persistence.action_executor import execute_actions

    run = IngestionRun(source="posts", status="running")
    session.add(run)
    session.flush()
    flow = FlowStats()
    seen_hashes: set[str] = set()
    found = 0

    images = sorted(p for g in _IMAGE_GLOBS for p in inbox.glob(g))
    for path in images:
        image_hash = dhash(path)
        if image_hash in seen_hashes:
            flow.processed_paths.append(path)     # duplicata: nao gasta interpretacao
            continue
        seen_hashes.add(image_hash)
        found += 1

        caption = handle = permalink = None
        sidecar = path.with_suffix(".json")
        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
                caption, handle, permalink = (meta.get("caption"), meta.get("handle"),
                                              meta.get("permalink"))
            except (ValueError, OSError):
                pass

        doc = Document(kind="ig_post", image_path=path, caption=caption,
                       handle=handle, permalink=permalink or f"flyer:{image_hash}")
        interp = interpreter.interpret(doc, _context_for(session, handle, reference))
        if interp is None:
            _log.warning("post %s: interpretacao falhou (codex) — failed/", path.name)
            flow.failed_paths.append(path)
            continue
        stats = execute_actions(session, doc, sanitize_actions(interp),
                                reference=reference)
        flow.created += stats["add"]
        if handle:
            _merge(flow.stats_by_handle.setdefault(handle, {}), stats)
        flow.processed_paths.append(path)
        session.commit()                          # progresso por post (runs longos)

    run.status = "finished"
    run.records_found = found
    run.records_created = flow.created
    run.finished_at = datetime.now(timezone.utc)
    session.commit()
    return flow
