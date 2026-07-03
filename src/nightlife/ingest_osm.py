# src/nightlife/ingest_osm.py
"""Ingere venues reais de SP do OpenStreetMap (Overpass) no banco.

Uso: .venv/Scripts/python -m nightlife.ingest_osm
Re-executar e seguro: matching reusa venues e a evidencia e idempotente.
"""
from __future__ import annotations

import truststore

# Usa o repositorio de certificados do WINDOWS em vez do bundle do certifi:
# antivirus como o Avast interceptam HTTPS re-assinando com CA propria (que so
# existe no cert store do SO) — sem isto, qualquer chamada real falha com
# CERTIFICATE_VERIFY_FAILED nesta maquina.
truststore.inject_into_ssl()

from datetime import date

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.osm_source import OSMSource
from .ingestion.pipeline import run_ingestion
from .models import DedupeCandidate, Venue


def main() -> None:
    source = OSMSource()
    with SessionLocal() as session:
        run = run_ingestion(session, source, reference=date.today(), label="osm")
        session.commit()
        venues = session.scalar(select(func.count()).select_from(Venue))
        reviews = session.scalar(
            select(func.count()).select_from(DedupeCandidate).where(
                DedupeCandidate.kind == "venue", DedupeCandidate.decision == "review",
            )
        )
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"DB agora: {venues} venues | venue matches em review: {reviews}")
        if run.errors:
            print("erros:\n" + run.errors)


if __name__ == "__main__":
    main()
