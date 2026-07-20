# src/nightlife/discover_ig_handles.py
"""Descobre @handles de IG pra nightclubs sem instagram, buscando na burner e
decidindo attach/review/reject via handle_match.decide (Ciclo E-2b). Zero
auto-envenenamento: so anexa em match forte; o resto vira review auditavel
(verification_logs), nunca silencioso.

Uso: .venv/Scripts/python -m nightlife.discover_ig_handles [--limit N]
"""
from __future__ import annotations

import argparse
import random
import time
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import SessionLocal
from .ingestion.handle_match import ProfileSignals, decide as _default_decide, shortlist
from .ingestion.ig_search import SearchResult, fetch_profile_signals, playwright_search
from .ingestion.instagram_source import open_context
from .models import Event, VerificationLog, Venue


def no_ig_venues(session: Session, *, limit: int | None = None) -> list[Venue]:
    """Nightclubs sem instagram (NULL ou ""), com os que tem evento futuro
    primeiro (mais urgentes de resolver) — cada grupo em ordem estavel por id."""
    base = select(Venue).where(
        Venue.category == "nightclub",
        (Venue.instagram.is_(None)) | (Venue.instagram == ""),
    ).order_by(Venue.id)
    venues = list(session.scalars(base).all())

    now = datetime.now(timezone.utc)
    future_ids = set(session.scalars(
        select(Event.venue_id).where(
            Event.venue_id.is_not(None),
            Event.starts_at >= now,
            Event.status != "cancelled",
        )
    ).all())

    with_event = [v for v in venues if v.id in future_ids]
    without_event = [v for v in venues if v.id not in future_ids]
    result = with_event + without_event
    if limit is not None:
        result = result[:limit]
    return result


def discover(session: Session, venues: list[Venue], *,
             search: Callable[[str], list[SearchResult]],
             profile: Callable[[str], "ProfileSignals | None"],
             decide=_default_decide,
             delay: Callable[[], None] = lambda: None) -> dict:
    """Nucleo injetavel (Ciclo E-2b): search/profile/decide/delay sao
    parametros pra testes usarem fakes, nunca a rede/IG real. Isolamento por
    venue: uma falha nao aborta o resto do lote."""
    stats = {"attach": 0, "review": 0, "reject": 0, "no_results": 0,
             "no_profile": 0, "error": 0}
    for venue in venues:
        try:
            results = search(venue.name)
            sl = shortlist(venue.name, results)
            if not sl:
                stats["no_results"] += 1
                session.add(VerificationLog(
                    entity_type="venue", entity_id=venue.id,
                    note=f"discover_ig: sem resultados de busca pra {venue.name}"))
            else:
                best = sl[0]
                signals = profile(best.username)
                if signals is None:
                    stats["no_profile"] += 1
                    session.add(VerificationLog(
                        entity_type="venue", entity_id=venue.id,
                        note=f"discover_ig: sem perfil pra @{best.username} (venue {venue.name})"))
                else:
                    decision = decide(venue_name=venue.name, venue_website=venue.website,
                                      venue_neighborhood=None, best=best, signals=signals)
                    if decision.action == "attach":
                        venue.instagram = decision.handle
                        session.add(VerificationLog(
                            entity_type="venue", entity_id=venue.id,
                            note=f"handle via ig_search: {decision.reason}"))
                        stats["attach"] += 1
                    elif decision.action == "review":
                        session.add(VerificationLog(
                            entity_type="venue", entity_id=venue.id,
                            note=f"handle candidato (review): @{decision.handle} — {decision.reason}"))
                        stats["review"] += 1
                    else:
                        stats["reject"] += 1
            session.commit()
        except Exception as exc:  # noqa: BLE001 — falha isolada por venue, run continua
            session.rollback()
            stats["error"] += 1
            session.add(VerificationLog(
                entity_type="venue", entity_id=venue.id,
                note=f"discover_ig erro: {exc}"))
            session.commit()
        delay()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    with SessionLocal() as session:
        venues = no_ig_venues(session, limit=args.limit)
        if not venues:
            print("nada a descobrir (nenhum nightclub sem instagram).")
            return
        pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
        try:
            stats = discover(
                session, venues,
                search=lambda q: playwright_search(context, q),
                profile=lambda h: fetch_profile_signals(context, h),
                delay=lambda: time.sleep(random.uniform(config.IG_DELAY_MIN, config.IG_DELAY_MAX)),
            )
        finally:
            context.close()
            pw.stop()
        print(stats)


if __name__ == "__main__":
    main()
