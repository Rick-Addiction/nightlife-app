# src/nightlife/ingest_sympla.py
"""Ingere eventos reais de festas/shows de SP da Sympla no banco.

Uso: .venv/Scripts/python -m nightlife.ingest_sympla
Re-executar e seguro: evidencia idempotente + dedupe por ticket_url.
"""
from __future__ import annotations

import truststore

# Cert store do Windows (antivirus intercepta TLS re-assinando com CA propria).
truststore.inject_into_ssl()

from datetime import date

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.pipeline import run_ingestion
from .ingestion.sympla_source import SymplaSource
from .models import Event, Organizer, Venue


def main() -> None:
    source = SymplaSource()
    with SessionLocal() as session:
        run = run_ingestion(session, source, reference=date.today(), label="sympla")
        session.commit()
        venues = session.scalar(select(func.count()).select_from(Venue))
        events = session.scalar(select(func.count()).select_from(Event))
        organizers = session.scalar(select(func.count()).select_from(Organizer))
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"DB agora: {venues} venues | {events} events | {organizers} organizers")
        if run.errors:
            print("erros:\n" + run.errors[:2000])


if __name__ == "__main__":
    main()
