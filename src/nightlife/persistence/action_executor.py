# src/nightlife/persistence/action_executor.py
"""Executa as acoes do interprete (spec E-1 §3.3). Cancel/update so com match
FORTE (nome normalizado + data; ou candidato unico) — mudanca destrutiva sem
certeza vira candidato auditavel em verification_logs."""
from __future__ import annotations

import unicodedata
from datetime import date
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.dates_ptbr import parse_ptbr_datetime
from ..extraction.post_actions import (
    AddEvent, CancelEvent, Ignore, PostInterpretation, UpdateEvent,
)
from ..ingestion.pipeline import venue_by_handle
from ..models import Event, VerificationLog
from .events_repo import upsert_event
from .inputs import EventInput, SourceInfo

if TYPE_CHECKING:
    from ..ingestion.post_interpreter import Document


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower().strip())
                   if unicodedata.category(c) != "Mn")


_SP_TZ = ZoneInfo("America/Sao_Paulo")


def _sp_day(dt) -> "date":
    # dia do CALENDARIO SP, nao UTC — festa sab 23h SP e domingo em UTC
    # (mesma licao do fix de datas do C-1)
    return dt.astimezone(_SP_TZ).date()


def _match_event(session: Session, venue_id: int | None, name: str,
                 date_text: str | None, *, reference: date) -> Event | None:
    """Match forte: mesmo venue + nome normalizado igual + (mesmo dia-SP OU
    candidato unico). Ambiguidade -> None (vira candidato, nunca chuta)."""
    if venue_id is None:
        return None
    candidates = [e for e in session.scalars(
        select(Event).where(Event.venue_id == venue_id, Event.status != "cancelled"))
        if _norm(e.name) == _norm(name)]
    if not candidates:
        return None
    if date_text:
        alvo = parse_ptbr_datetime(date_text, reference=reference).dt
        if alvo is not None:
            same_day = [e for e in candidates
                        if e.starts_at is not None and _sp_day(e.starts_at) == _sp_day(alvo)]
            if len(same_day) == 1:
                return same_day[0]
            return None
    return candidates[0] if len(candidates) == 1 else None


def _do_add(session: Session, doc: "Document", a: AddEvent, *, reference: date) -> None:
    starts = None
    if a.date_text:
        starts = parse_ptbr_datetime(a.date_text, reference=reference).dt
    venue = venue_by_handle(session, doc.handle)
    raw_fields: dict = {"raw": a.model_dump_json()}
    if venue is not None:
        raw_fields["anchored_by"] = "ig_handle"
    upsert_event(
        session,
        EventInput(name=a.name, starts_at=starts,
                   venue_id=venue.id if venue is not None else None,
                   genre=a.genre, ticket_url=a.ticket_url,
                   lineup_text=", ".join(a.lineup) or None,
                   raw_fields=raw_fields),
        SourceInfo(source_type="vision_flyer", source_url=doc.permalink,
                   raw_payload=a.model_dump_json()),
        reference=reference,
    )


def execute_actions(session: Session, doc: "Document",
                    interp: PostInterpretation, *, reference: date) -> dict:
    stats: dict = {"add": 0, "cancel": 0, "cancel_candidate": 0,
                   "update": 0, "ignore": {}}
    venue = venue_by_handle(session, doc.handle)
    vid = venue.id if venue is not None else None

    for a in interp.actions:
        if isinstance(a, AddEvent):
            _do_add(session, doc, a, reference=reference)
            stats["add"] += 1
        elif isinstance(a, CancelEvent):
            ev = _match_event(session, vid, a.event_name, a.event_date_text,
                              reference=reference)
            if ev is not None:
                ev.status = "cancelled"
                session.add(VerificationLog(
                    entity_type="event", entity_id=ev.id,
                    note=f"cancelado via ig_post {doc.permalink} (quote: {a.quote!r})"))
                stats["cancel"] += 1
            else:
                session.add(VerificationLog(
                    entity_type="venue", entity_id=vid or 0,
                    note=(f"cancel_candidate: {a.event_name!r} "
                          f"({a.event_date_text or 'sem data'}) via {doc.permalink} "
                          f"(quote: {a.quote!r}) — sem match forte")))
                stats["cancel_candidate"] += 1
        elif isinstance(a, UpdateEvent):
            ev = _match_event(session, vid, a.event_name, a.event_date_text,
                              reference=reference)
            if ev is not None:
                if "date_text" in a.changes:
                    novo = parse_ptbr_datetime(a.changes["date_text"], reference=reference).dt
                    if novo is not None:
                        ev.starts_at = novo
                if "name" in a.changes:
                    ev.name = a.changes["name"]
                if "ticket_url" in a.changes:
                    ev.ticket_url = a.changes["ticket_url"]
                session.add(VerificationLog(
                    entity_type="event", entity_id=ev.id,
                    note=f"atualizado via ig_post {doc.permalink} (quote: {a.quote!r})"))
                stats["update"] += 1
            else:
                # "adiada para X" de festa que nao temos = festa nova com data X
                add = AddEvent(name=a.changes.get("name", a.event_name),
                               date_text=a.changes.get("date_text", a.event_date_text),
                               ticket_url=a.changes.get("ticket_url"),
                               quotes={"name": a.quote or a.event_name},
                               confidence={"name": a.confidence})
                _do_add(session, doc, add, reference=reference)
                stats["add"] += 1
        elif isinstance(a, Ignore):
            stats["ignore"][a.reason] = stats["ignore"].get(a.reason, 0) + 1
    return stats
