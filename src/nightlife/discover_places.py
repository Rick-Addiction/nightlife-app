"""Descobre venues de vida noturna via Google Places Nearby e ingere pelo
pipeline. Sob demanda (fora do daily): venue novo e raro e cada chamada custa.

Uso: .venv/Scripts/python -m nightlife.discover_places
     .venv/Scripts/python -m nightlife.discover_places --seed "baixa augusta" --radius 400 --max-depth 5
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ingestion.pipeline import run_ingestion
from .ingestion.places_source import (
    _MAX_SUBDIVIDE_DEPTH, _MIN_SUBDIVIDE_RADIUS_M, _SEARCH_RADIUS_M, PlacesSource,
)
from .models import IngestionRun, Venue

_SP_TZ = ZoneInfo("America/Sao_Paulo")


def discover(session: Session, source: PlacesSource, *, reference: date) -> IngestionRun:
    return run_ingestion(session, source, reference=reference, label="places")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", help="substring (normalizada) do bairro-semente; sem isso varre TODAS")
    ap.add_argument("--radius", type=float, default=_SEARCH_RADIUS_M, help="metros (default 1000)")
    ap.add_argument("--max-depth", type=int, default=_MAX_SUBDIVIDE_DEPTH,
                    help="profundidade maxima de subdivisao ao saturar (default 3)")
    args = ap.parse_args(argv)

    from .config import GOOGLE_MAPS_API_KEY

    if not GOOGLE_MAPS_API_KEY:
        print("ERRO: defina GOOGLE_MAPS_API_KEY (e habilite a Places API New no Google Cloud)")
        sys.exit(1)

    import truststore
    truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

    from .db import SessionLocal
    from .ingestion.places_client import PlacesClient

    kwargs = {"radius": args.radius, "max_depth": args.max_depth,
              "min_radius": _MIN_SUBDIVIDE_RADIUS_M}
    if args.seed:
        # reusa a normalizacao/resolucao de bairro do sweep_area (mesmo
        # criterio: substring normalizada, empate = label mais especifico)
        from .sweep_area import resolve_bairro
        label, lat, lng = resolve_bairro(args.seed)
        kwargs["seeds"] = [(label, lat, lng)]

    today = datetime.now(_SP_TZ).date()
    with SessionLocal() as session:
        run = discover(session, PlacesSource(PlacesClient(GOOGLE_MAPS_API_KEY), **kwargs),
                       reference=today)
        session.commit()
        total = session.scalar(select(func.count()).select_from(Venue))
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"DB: {total} venues")
        if run.errors:
            print("erros:\n" + run.errors[:2000])
        if run.status == "error":
            sys.exit(1)  # scriptavel: falha do run vira exit code


if __name__ == "__main__":
    main()
