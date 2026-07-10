# src/nightlife/backfill_handle_anchor.py
"""One-off: ancora eventos de flyer que ficaram sem venue, via handle do
sidecar em flyers/processed/ (a ancoragem por handle so passou a existir no
pipeline no Ciclo D-1). Uso: .venv/Scripts/python -m nightlife.backfill_handle_anchor"""
from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .ingestion.pipeline import _venue_by_handle
from .models import Event, EventSource

_IG_PERMALINK = re.compile(r"instagram\.com/p/([A-Za-z0-9_-]+)")
PROCESSED_DIR = Path("flyers") / "processed"


def backfill(session: Session, *, processed_dir: Path = PROCESSED_DIR) -> int:
    anchored = 0
    rows = session.execute(
        select(Event, EventSource.source_url)
        .join(EventSource, EventSource.event_id == Event.id)
        .where(Event.venue_id.is_(None), EventSource.source_type == "vision_flyer",
               EventSource.source_url.is_not(None))
    ).all()
    for event, url in rows:
        m = _IG_PERMALINK.search(url or "")
        if not m:
            continue
        sidecar = processed_dir / f"{m.group(1)}.json"
        if not sidecar.exists():
            continue
        try:
            handle = json.loads(sidecar.read_text(encoding="utf-8")).get("handle")
        except (ValueError, OSError):
            continue
        venue = _venue_by_handle(session, handle)
        if venue is not None and event.venue_id is None:
            event.venue_id = venue.id
            anchored += 1
    return anchored


def main() -> None:
    with SessionLocal() as session:
        n = backfill(session)
        session.commit()
        print(f"ancorados: {n} eventos")


if __name__ == "__main__":
    main()
