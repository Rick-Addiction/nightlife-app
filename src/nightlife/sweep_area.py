# src/nightlife/sweep_area.py
"""Varredura de IG por AREA (Ciclo D-1): scrape de todos os handles do
circulo (sem cap — decisao do spec), extracao dos flyers, diff e report
por local. CLI: --bairro <nome> [--km 2] | --center lat,lng --km r
[--sweep-id N (uso da API)]."""
from __future__ import annotations

import argparse
import random
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import config
from .db import SessionLocal
from .ingestion.places_source import SEED_POINTS
from .models import AreaSweep, Event, EventSource, Venue
from .persistence.ig_state import (
    get_or_create_state, handles_in_area, record_failure, record_success,
    record_venue_activity,
)

FLYERS_DIR = Path("flyers")
DEFAULT_KM = 2.0


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) != "Mn")


def resolve_bairro(nome: str) -> tuple[str, float, float]:
    """Match por substring normalizada contra as sementes; 1o match vence.
    Nenhum match -> ValueError listando os validos."""
    alvo = _norm(nome)
    for label, lat, lng in SEED_POINTS:
        if alvo in _norm(label):
            return label, lat, lng
    validos = ", ".join(label for label, _, _ in SEED_POINTS)
    raise ValueError(f"bairro {nome!r} nao encontrado. Validos: {validos}")


def snapshot_future(session: Session) -> dict:
    """Estado 'antes' pro diff: ids de eventos futuros e venues que ja tem festa."""
    now = datetime.now(timezone.utc)
    events = set(session.scalars(select(Event.id).where(Event.starts_at > now)).all())
    venues = set(session.scalars(
        select(Event.venue_id).where(Event.starts_at > now, Event.venue_id.is_not(None))).all())
    return {"event_ids": events, "venue_ids": venues}


def compute_diff(session: Session, before: dict) -> dict:
    now = datetime.now(timezone.utc)
    events = set(session.scalars(select(Event.id).where(Event.starts_at > now)).all())
    venue_ids = set(session.scalars(
        select(Event.venue_id).where(Event.starts_at > now, Event.venue_id.is_not(None))).all())
    ganharam = venue_ids - before["venue_ids"]
    nomes = sorted(session.scalars(select(Venue.name).where(Venue.id.in_(ganharam))).all()) if ganharam else []
    return {"novas_festas": len(events - before["event_ids"]),
            "venues_com_pin_novo": nomes}


def _events_for_shortcodes(session: Session, shortcodes: list[str]) -> list[dict]:
    out: list[dict] = []
    for sc in shortcodes:
        rows = session.execute(
            select(Event).join(EventSource, EventSource.event_id == Event.id)
            .where(EventSource.source_type == "vision_flyer",
                   EventSource.source_url.like(f"%/p/{sc}%"))
        ).scalars().all()
        for ev in rows:
            out.append({"event_id": ev.id, "name": ev.name,
                        "starts_at": ev.starts_at.isoformat() if ev.starts_at else None,
                        "anchored": ev.venue_id is not None})
    return out


def run_sweep(session: Session, sweep: AreaSweep, *, inbox: Path,
              scrape: Callable, extract: Callable[[], None],
              delay: Callable[[], None]) -> None:
    """Nucleo testavel: scrape/extract/delay injetaveis. Blindado por handle."""
    before = snapshot_future(session)
    handles = handles_in_area(session, sweep.center_lat, sweep.center_lng, sweep.radius_km)
    venues_by_handle = {v.instagram: v for v in session.scalars(
        select(Venue).where(Venue.instagram.in_(handles)))} if handles else {}
    sweep.total_handles = len(handles)
    sweep.phase = "varrendo"
    session.commit()

    for handle in handles:
        st = get_or_create_state(session, handle)
        v = venues_by_handle.get(handle)
        item = {"venue_id": v.id if v else None, "venue_name": v.name if v else None,
                "handle": handle, "status": "ok", "posts_novos": 0,
                "flyers": [], "festas": []}
        stems_before = {p.stem for p in inbox.glob("*.json")}
        try:
            result = scrape(handle, st)
            record_success(st, result.last_shortcode)
            record_venue_activity(session, handle, result.latest_post_at)
            item["posts_novos"] = result.downloaded
            item["flyers"] = sorted({p.stem for p in inbox.glob("*.json")} - stems_before)
        except Exception as exc:  # noqa: BLE001 — falha isolada por handle
            record_failure(st)
            item["status"] = "falha"
            item["erro"] = str(exc)[:300]
        sweep.report = [*sweep.report, item]
        flag_modified(sweep, "report")
        session.commit()
        delay()

    sweep.phase = "extraindo"
    session.commit()
    try:
        extract()
    except Exception as exc:  # noqa: BLE001 — extracao inteira falhou: reporta, nao trava
        sweep.error = f"extracao: {exc}"[:500]
    # casa festas criadas de volta aos itens (por shortcode do permalink)
    report = sweep.report
    for item in report:
        if item["flyers"]:
            item["festas"] = _events_for_shortcodes(session, item["flyers"])
    sweep.report = report
    flag_modified(sweep, "report")
    sweep.diff = compute_diff(session, before)
    sweep.phase = "done"
    sweep.status = "error" if sweep.error else "done"
    sweep.finished_at = datetime.now(timezone.utc)
    session.commit()


def _real_scrape_factory(context):
    from .ingestion.instagram_source import (
        ScrapeConfig, playwright_download, playwright_fetch_posts, scrape_handle,
    )

    def _scrape(handle, st):
        cap = (config.IG_MAX_POSTS_FIRST_SWEEP if st.last_shortcode is None
               else config.IG_MAX_POSTS_INCREMENTAL)
        return scrape_handle(
            handle, last_shortcode=st.last_shortcode,
            fetch_posts=lambda h: playwright_fetch_posts(context, h),
            download=lambda p, d: playwright_download(context, p, d),
            config=ScrapeConfig(inbox=FLYERS_DIR, cap=cap),
        )
    return _scrape


def _real_extract(session: Session) -> None:
    import shutil
    from .ingest_flyers import _move_all
    from .ingestion.codex_extractor import CodexExtractor
    from .ingestion.flyer_source import FlyerSource
    from .ingestion.pipeline import run_ingestion
    if shutil.which("codex") is None:
        raise RuntimeError("codex CLI nao encontrado no PATH")
    source = FlyerSource(FLYERS_DIR, CodexExtractor(), reference=date.today())
    run_ingestion(session, source, reference=date.today(), label="flyers")
    session.commit()
    _move_all(source.processed_paths, FLYERS_DIR / "processed")
    _move_all(source.failed_paths, FLYERS_DIR / "failed")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bairro")
    g.add_argument("--center", help="lat,lng")
    ap.add_argument("--km", type=float, default=DEFAULT_KM)
    ap.add_argument("--sweep-id", type=int, default=None, help="registro criado pela API")
    args = ap.parse_args(argv)

    FLYERS_DIR.mkdir(exist_ok=True)
    with SessionLocal() as session:
        if args.sweep_id is not None:
            sweep = session.get(AreaSweep, args.sweep_id)
            if sweep is None:
                raise SystemExit(f"AreaSweep #{args.sweep_id} nao existe")
        else:
            running = session.scalars(
                select(AreaSweep).where(AreaSweep.status == "running")).first()
            if running is not None:
                raise SystemExit(f"ja existe varredura rodando (#{running.id}) — aguarde ou "
                                 f"marque status='error' manualmente se ela morreu")
            if args.bairro:
                label, lat, lng = resolve_bairro(args.bairro)
            else:
                lat, lng = (float(x) for x in args.center.split(","))
                label = None
            sweep = AreaSweep(label=label, center_lat=lat, center_lng=lng,
                              radius_km=args.km, started_at=datetime.now(timezone.utc))
            session.add(sweep)
            session.commit()

        from .ingestion.instagram_source import open_context
        pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
        try:
            run_sweep(session, sweep, inbox=FLYERS_DIR,
                      scrape=_real_scrape_factory(context),
                      extract=lambda: _real_extract(session),
                      delay=lambda: time.sleep(random.uniform(config.IG_DELAY_MIN,
                                                              config.IG_DELAY_MAX)))
        except Exception as exc:  # noqa: BLE001 — marca o sweep, nao deixa running orfao
            sweep.status = "error"
            sweep.error = str(exc)[:500]
            sweep.finished_at = datetime.now(timezone.utc)
            session.commit()
            raise
        finally:
            context.close()
            pw.stop()
        d = sweep.diff or {}
        print(f"sweep #{sweep.id} {sweep.status}: +{d.get('novas_festas', 0)} festas, "
              f"venues com pin novo: {d.get('venues_com_pin_novo', [])}")


if __name__ == "__main__":
    main()
