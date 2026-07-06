# src/nightlife/ingest_ra.py
"""Ingere eventos de SP do Resident Advisor no banco.

Uso: .venv/Scripts/python -m nightlife.ingest_ra
"""
from __future__ import annotations

import truststore

truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

from datetime import date

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.pipeline import run_ingestion
from .ingestion.ra_source import RASource
from .models import Event, Venue


def main() -> None:
    with SessionLocal() as session:
        run = run_ingestion(session, RASource(reference=date.today()),
                            reference=date.today(), label="ra")
        session.commit()
        venues = session.scalar(select(func.count()).select_from(Venue))
        events = session.scalar(select(func.count()).select_from(Event))
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"DB: {venues} venues | {events} events")
        if run.errors:
            print("erros:\n" + run.errors[:2000])


if __name__ == "__main__":
    main()
