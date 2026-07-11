# src/nightlife/ingest_flyers.py
"""Ingere flyers do inbox flyers/ no banco (extracao via codex CLI).

Uso: coloque imagens em flyers/ e rode
  .venv/Scripts/python -m nightlife.ingest_flyers
Processadas vao para flyers/processed/; falhas para flyers/failed/.
"""
from __future__ import annotations

import shutil
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.codex_extractor import CodexExtractor
from .ingestion.flyer_source import FlyerSource
from .ingestion.pipeline import run_ingestion
from .models import Event

FLYERS_DIR = Path("flyers")


def move_all(paths: list[Path], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for p in paths:
        for f in (p, p.with_suffix(".json")):  # imagem + sidecar (se houver)
            if not f.exists():
                continue
            target = dest / f.name
            if target.exists():
                target.unlink()
            shutil.move(str(f), str(target))


def main() -> None:
    if shutil.which("codex") is None:
        print("ERRO: codex CLI nao encontrado no PATH (instale/logue o Codex).")
        sys.exit(1)
    FLYERS_DIR.mkdir(exist_ok=True)

    source = FlyerSource(FLYERS_DIR, CodexExtractor(), reference=date.today())
    with SessionLocal() as session:
        run = run_ingestion(session, source, reference=date.today(), label="flyers")
        session.commit()
        events = session.scalar(select(func.count()).select_from(Event))
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"processadas={len(source.processed_paths)} "
              f"falhas={len(source.failed_paths)} | DB: {events} events")
        if run.errors:
            print("erros:\n" + run.errors[:2000])

    move_all(source.processed_paths, FLYERS_DIR / "processed")
    move_all(source.failed_paths, FLYERS_DIR / "failed")


if __name__ == "__main__":
    main()
