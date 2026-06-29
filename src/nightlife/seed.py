# src/nightlife/seed.py
"""Roda o pipeline de ingestao com as fixtures mock contra o banco real.

Uso: .venv/Scripts/python -m nightlife.seed
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.mock_source import MockSource
from .ingestion.pipeline import run_ingestion
from .models import Event, Venue

FIXTURES = Path(__file__).parent / "fixtures"


def main() -> None:
    source = MockSource.from_fixtures(FIXTURES / "venues.json", FIXTURES / "event_pages.json")
    with SessionLocal() as session:
        run = run_ingestion(session, source, reference=date.today())
        session.commit()
        venues = session.scalar(select(func.count()).select_from(Venue))
        events = session.scalar(select(func.count()).select_from(Event))
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"DB agora: {venues} venues, {events} events")
        if run.errors:
            print("erros:\n" + run.errors)


if __name__ == "__main__":
    main()
