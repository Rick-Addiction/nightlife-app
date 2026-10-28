# src/nightlife/ingest_shotgun.py
"""Ingere eventos de SP do Shotgun (shotgun.live) no banco.

Uso: .venv/Scripts/python -m nightlife.ingest_shotgun [--horizon-days N]
Re-executar e seguro: evidencia idempotente + dedupe por ticket_url/nome+data.
"""
from __future__ import annotations

import truststore

truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.pipeline import run_ingestion
from .ingestion.shotgun_source import ShotgunSource
from .models import Event, Venue

_SP_TZ = ZoneInfo("America/Sao_Paulo")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon-days", type=int, default=45)
    args = ap.parse_args()
    today = datetime.now(_SP_TZ).date()  # "dia" ancorado em SP (disciplina do projeto)
    with SessionLocal() as session:
        run = run_ingestion(session, ShotgunSource(reference=today, horizon_days=args.horizon_days),
                            reference=today, label="shotgun")
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
