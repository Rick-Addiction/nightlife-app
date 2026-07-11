# src/nightlife/ingest_flyers.py
"""Ingere flyers do inbox flyers/ no banco (extracao via codex CLI).

Uso: coloque imagens em flyers/ e rode
  .venv/Scripts/python -m nightlife.ingest_flyers
Processadas vao para flyers/processed/; falhas para flyers/failed/ (movidas
post a post por process_inbox, nao no fim do lote — ver post_flow.py B4).
"""
from __future__ import annotations

import shutil
import sys
from datetime import date
from pathlib import Path

from .db import SessionLocal
from .ingestion.post_flow import process_inbox
from .ingestion.post_interpreter import PostInterpreter

FLYERS_DIR = Path("flyers")


def main() -> None:
    if shutil.which("codex") is None:
        print("ERRO: codex CLI nao encontrado no PATH (instale/logue o Codex).")
        sys.exit(1)
    FLYERS_DIR.mkdir(exist_ok=True)

    with SessionLocal() as session:
        flow = process_inbox(session, FLYERS_DIR, PostInterpreter(), reference=date.today())
        print(f"posts: {len(flow.processed_paths)} processados, "
              f"{len(flow.failed_paths)} falhas | eventos criados: {flow.created}")


if __name__ == "__main__":
    main()
