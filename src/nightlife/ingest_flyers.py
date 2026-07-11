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

from .db import SessionLocal
from .ingestion.post_flow import process_inbox
from .ingestion.post_interpreter import PostInterpreter

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

    with SessionLocal() as session:
        flow = process_inbox(session, FLYERS_DIR, PostInterpreter(), reference=date.today())
        session.commit()
        print(f"posts: {len(flow.processed_paths)} processados, "
              f"{len(flow.failed_paths)} falhas | eventos criados: {flow.created}")

    move_all(flow.processed_paths, FLYERS_DIR / "processed")
    move_all(flow.failed_paths, FLYERS_DIR / "failed")


if __name__ == "__main__":
    main()
