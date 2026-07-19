"""Varre os venues com SITE PROPRIO e extrai a agenda (Ciclo E-2a). Semanal.
Uso: .venv/Scripts/python -m nightlife.crawl_sites [--limit N]"""
from __future__ import annotations

import argparse
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .ingestion.post_interpreter import PostInterpreter
from .ingestion.web_flow import crawl_venue
from .ingestion.web_source import fetch_page
from .models import IngestionRun, Venue

_EXCLUDE = ("%instagram.com%", "%facebook.com%", "%linktr%", "%linktree%")


def own_site_venues(session: Session) -> list[Venue]:
    q = select(Venue).where(Venue.website.is_not(None))
    for pat in _EXCLUDE:
        q = q.where(~Venue.website.ilike(pat))
    return list(session.scalars(q.order_by(Venue.id)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    today = date.today()
    with SessionLocal() as session:
        run = IngestionRun(source="sites", status="running")
        session.add(run); session.flush()
        venues = own_site_venues(session)
        if args.limit:
            venues = venues[: args.limit]
        interpreter = PostInterpreter()
        total_add = found = 0
        for v in venues:
            found += 1
            try:
                stats = crawl_venue(session, v, fetcher=fetch_page,
                                    interpreter=interpreter, reference=today)
                total_add += stats.get("add", 0)
                mark = "PULOU" if stats.get("skipped") else f"+{stats.get('add',0)}"
                print(f"  {v.name[:34]:36} {mark} (jsonld={stats.get('jsonld',0)} codex={stats.get('codex',0)})")
            except Exception as exc:  # noqa: BLE001 — falha isolada por venue
                print(f"  {v.name[:34]:36} ERRO: {str(exc)[:60]}")
        run.status = "finished"; run.records_found = found; run.records_created = total_add
        from datetime import datetime, timezone
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        print(f"sites: {found} venues, +{total_add} eventos")


if __name__ == "__main__":
    main()
