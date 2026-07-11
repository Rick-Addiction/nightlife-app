# src/nightlife/ingestion/post_flow.py
"""Orquestra o inbox de posts (spec E-1 §3.4): dHash dedupe -> Document ->
interprete -> saneamento -> executor. Cada post e movido pra processed/failed
IMEDIATAMENTE apos seu commit (nao acumulado ate o fim do inbox — runs longos
nao perdem o progresso ja persistido se o processo morrer no meio).
IngestionRun label='posts'."""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..extraction.imagehash import dhash
from ..extraction.post_actions import sanitize_actions
from ..models import Event, IngestionRun
from .pipeline import venue_by_handle
from .post_interpreter import Document, PostInterpreter, VenueContext

_log = logging.getLogger(__name__)
_IMAGE_GLOBS = ("*.jpg", "*.jpeg", "*.png", "*.webp")
_SP_TZ = ZoneInfo("America/Sao_Paulo")
_KNOWN_CAP = 20


def move_all(paths: list[Path], dest: Path) -> None:
    """Move imagem + sidecar (.json, se houver) pra dest/. Mora aqui (nao em
    ingest_flyers.py) pra evitar import circular: ingest_flyers importa
    process_inbox deste modulo, entao este modulo nao pode importar de volta
    de ingest_flyers."""
    dest.mkdir(parents=True, exist_ok=True)
    for p in paths:
        for f in (p, p.with_suffix(".json")):
            if not f.exists():
                continue
            target = dest / f.name
            if target.exists():
                target.unlink()
            shutil.move(str(f), str(target))


@dataclass
class FlowStats:
    processed_paths: list[Path] = field(default_factory=list)
    failed_paths: list[Path] = field(default_factory=list)
    stats_by_handle: dict[str, dict] = field(default_factory=dict)
    created: int = 0


def _context_for(session: Session, handle: str | None, today: date) -> VenueContext:
    venue = venue_by_handle(session, handle)  # B6: DRY — mesma resolucao do executor
    known: list[tuple[str, str | None]] = []
    if venue is not None:
        now = datetime.now(timezone.utc)
        # B5: filtro futuro-ou-sem-data JA NO SQL, antes do LIMIT — senao
        # 20+ eventos passados esgotam o cap e os futuros (o que importa pro
        # interprete decidir repost/adiamento) nunca entram no contexto.
        rows = session.scalars(
            select(Event).where(
                Event.venue_id == venue.id,
                Event.status != "cancelled",
                or_(Event.starts_at >= now, Event.starts_at.is_(None)),
            ).order_by(Event.starts_at.asc().nullslast()).limit(_KNOWN_CAP))
        for e in rows:
            known.append((e.name, e.starts_at.date().isoformat() if e.starts_at else None))
    return VenueContext(venue_name=venue.name if venue else None, handle=handle,
                        today_iso=today.isoformat(), known_events=known)


def _merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if k == "ignore":
            ig = dst.setdefault("ignore", {})
            for r, n in v.items():
                ig[r] = ig.get(r, 0) + n
        else:
            dst[k] = dst.get(k, 0) + v


def process_inbox(session: Session, inbox: Path, interpreter: PostInterpreter,
                  *, reference: date, log=print,
                  processed_dir: Path | None = None,
                  failed_dir: Path | None = None) -> FlowStats:
    from ..persistence.action_executor import execute_actions

    processed_dir = processed_dir or inbox / "processed"
    failed_dir = failed_dir or inbox / "failed"

    run = IngestionRun(source="posts", status="running")
    session.add(run)
    session.flush()
    flow = FlowStats()
    seen_hashes: set[str] = set()
    found = 0

    try:
        images = sorted(p for g in _IMAGE_GLOBS for p in inbox.glob(g))
        for path in images:
            image_hash = dhash(path)
            if image_hash in seen_hashes:
                # duplicata: nao gasta interpretacao. WHY (B9/M5): repost de
                # imagem IDENTICA com legenda nova (ex: cancelamento) e pulado
                # nesta rodada — aceito, porque cancelamento costuma vir com
                # imagem/carimbo proprio ("CANCELADA"), nao um repost do flyer
                # original.
                flow.processed_paths.append(path)
                move_all([path], processed_dir)
                continue
            seen_hashes.add(image_hash)
            found += 1

            caption = handle = permalink = None
            sidecar = path.with_suffix(".json")
            if sidecar.exists():
                try:
                    meta = json.loads(sidecar.read_text(encoding="utf-8"))
                    caption, handle, permalink = (meta.get("caption"), meta.get("handle"),
                                                  meta.get("permalink"))
                except (ValueError, OSError):
                    pass

            doc = Document(kind="ig_post", image_path=path, caption=caption,
                           handle=handle, permalink=permalink or f"flyer:{image_hash}")
            interp = interpreter.interpret(doc, _context_for(session, handle, reference))
            if interp is None:
                _log.warning("post %s: interpretacao falhou (codex) — failed/", path.name)
                flow.failed_paths.append(path)
                move_all([path], failed_dir)
                continue
            stats = execute_actions(session, doc, sanitize_actions(interp),
                                    reference=reference)
            flow.created += stats["add"]
            if handle:
                _merge(flow.stats_by_handle.setdefault(handle, {}), stats)
            flow.processed_paths.append(path)
            session.commit()                          # progresso por post (runs longos)
            move_all([path], processed_dir)            # B4: move JA, nao no fim do inbox

        run.status = "finished"
        run.records_found = found
        run.records_created = flow.created
    except Exception as exc:
        run.status = "error"
        run.errors = str(exc)[:500]
        raise
    finally:
        # WHY (B4): um run preso em 'running' e aceitavel como registro —
        # nada trava nele — mas o finally cobre o caminho comum (sucesso ou
        # excecao inesperada) sem deixar o IngestionRun orfao.
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
    return flow
