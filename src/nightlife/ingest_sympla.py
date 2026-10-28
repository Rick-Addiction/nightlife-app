# src/nightlife/ingest_sympla.py
"""Ingere eventos reais de festas/shows de SP da Sympla no banco.

Uso: .venv/Scripts/python -m nightlife.ingest_sympla [--q TERMO ...]
Sem --q: varredura completa da cidade. Com --q: uma passada de busca por
termo (ex.: --q halloween --q techno) — util pra datas tematicas, em que a
varredura por relevancia da API pode nao alcancar tudo.
Re-executar e seguro: evidencia idempotente + dedupe por ticket_url.
"""
from __future__ import annotations

import truststore

# Cert store do Windows (antivirus intercepta TLS re-assinando com CA propria).
truststore.inject_into_ssl()

import argparse
from datetime import date

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.pipeline import run_ingestion
from .ingestion.sympla_source import SymplaSource
from .models import Event, Organizer, Venue


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", action="append", default=None,
                    help="termo de busca (repetivel); sem ele, varredura completa de SP")
    args = ap.parse_args()
    queries: list[str | None] = args.q or [None]
    with SessionLocal() as session:
        for q in queries:
            run = run_ingestion(session, SymplaSource(query=q), reference=date.today(),
                                label="sympla")
            session.commit()
            print(f"IngestionRun #{run.id} (q={q or '-'}): status={run.status} "
                  f"found={run.records_found} created={run.records_created}")
            if run.errors:
                print("erros:\n" + run.errors[:2000])
        venues = session.scalar(select(func.count()).select_from(Venue))
        events = session.scalar(select(func.count()).select_from(Event))
        organizers = session.scalar(select(func.count()).select_from(Organizer))
        print(f"DB agora: {venues} venues | {events} events | {organizers} organizers")


if __name__ == "__main__":
    main()
