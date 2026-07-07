"""Descobre venues de vida noturna via Google Places Nearby e ingere pelo
pipeline. Sob demanda (fora do daily): venue novo e raro e cada chamada custa.

Uso: .venv/Scripts/python -m nightlife.discover_places
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ingestion.pipeline import run_ingestion
from .ingestion.places_source import PlacesSource
from .models import IngestionRun, Venue

_SP_TZ = ZoneInfo("America/Sao_Paulo")


def discover(session: Session, source: PlacesSource, *, reference: date) -> IngestionRun:
    return run_ingestion(session, source, reference=reference, label="places")


def main() -> None:
    from .config import GOOGLE_MAPS_API_KEY

    if not GOOGLE_MAPS_API_KEY:
        print("ERRO: defina GOOGLE_MAPS_API_KEY (e habilite a Places API New no Google Cloud)")
        sys.exit(1)

    import truststore
    truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

    from .db import SessionLocal
    from .ingestion.places_client import PlacesClient

    today = datetime.now(_SP_TZ).date()
    with SessionLocal() as session:
        run = discover(session, PlacesSource(PlacesClient(GOOGLE_MAPS_API_KEY)), reference=today)
        session.commit()
        total = session.scalar(select(func.count()).select_from(Venue))
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"DB: {total} venues")
        if run.errors:
            print("erros:\n" + run.errors[:2000])


if __name__ == "__main__":
    main()
