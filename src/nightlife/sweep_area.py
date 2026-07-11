# src/nightlife/sweep_area.py
"""Varredura de IG por AREA (Ciclo D-1): scrape de todos os handles do
circulo (sem cap — decisao do spec), extracao dos flyers, diff e report
por local. CLI: --bairro <nome> [--km 2] | --center lat,lng --km r
[--sweep-id N (uso da API)]."""
from __future__ import annotations

import argparse
import random
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
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
_IG_PERMALINK = re.compile(r"instagram\.com/p/([A-Za-z0-9_-]+)")


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) != "Mn")


def resolve_bairro(nome: str) -> tuple[str, float, float]:
    """Match por substring normalizada contra as sementes; empate -> label MAIS
    CURTO (mais especifico) vence (ex.: 'augusta' nao deve perder pra 'Baixa
    Augusta/Consolacao' so por ordem de lista). Nenhum match -> ValueError
    listando os validos."""
    alvo = _norm(nome)
    matches = [(label, lat, lng) for label, lat, lng in SEED_POINTS if alvo in _norm(label)]
    if not matches:
        validos = ", ".join(label for label, _, _ in SEED_POINTS)
        raise ValueError(f"bairro {nome!r} nao encontrado. Validos: {validos}")
    return min(matches, key=lambda t: len(t[0]))


def snapshot_future(session: Session) -> dict:
    """Estado 'antes' pro diff: ids de eventos futuros e venues que ja tem festa."""
    now = datetime.now(timezone.utc)
    events = set(session.scalars(select(Event.id).where(Event.starts_at > now)).all())
    venues = set(session.scalars(
        select(Event.venue_id).where(Event.starts_at > now, Event.venue_id.is_not(None))).all())
    return {"event_ids": events, "venue_ids": venues}


def compute_diff(session: Session, before: dict) -> dict:
    # WHY: o diff credita qualquer evento criado na janela do sweep (nao so os
    # que vieram DESTE sweep) — um daily concorrente rodando ao mesmo tempo
    # contaminaria o numero. Aceito: app pessoal, runs sao manuais/unicos.
    # novas_festas conta so eventos FUTUROS: um flyer extraido de uma festa ja
    # passada aparece no report do local (por handle), mas nao no diff da area.
    now = datetime.now(timezone.utc)
    events = set(session.scalars(select(Event.id).where(Event.starts_at > now)).all())
    venue_ids = set(session.scalars(
        select(Event.venue_id).where(Event.starts_at > now, Event.venue_id.is_not(None))).all())
    ganharam = venue_ids - before["venue_ids"]
    nomes = sorted(session.scalars(select(Venue.name).where(Venue.id.in_(ganharam))).all()) if ganharam else []
    return {"novas_festas": len(events - before["event_ids"]),
            "venues_com_pin_novo": nomes}


def _events_for_shortcodes(session: Session, shortcodes: list[str]) -> list[dict]:
    """Casa flyers por shortcode EXATO do permalink. NAO usar LIKE '%/p/{sc}%':
    '/p/SC1' tambem casaria '/p/SC12/', e '_' e wildcard do LIKE mas faz parte
    do alfabeto de shortcode do IG — falso-positivo garantido."""
    if not shortcodes:
        return []
    by_shortcode: dict[str, list[Event]] = {}
    rows = session.execute(
        select(Event, EventSource.source_url)
        .join(EventSource, EventSource.event_id == Event.id)
        .where(EventSource.source_type == "vision_flyer")
    ).all()
    for ev, url in rows:
        m = _IG_PERMALINK.search(url or "")
        if m:
            by_shortcode.setdefault(m.group(1), []).append(ev)
    out: list[dict] = []
    for sc in shortcodes:
        for ev in by_shortcode.get(sc, []):
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
        # B2: erro de DB dentro de extract() deixa a sessao em transacao
        # falha; sem rollback, a query/commit seguinte estoura PendingRollbackError.
        session.rollback()
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
    from .ingest_flyers import move_all
    from .ingestion.codex_extractor import CodexExtractor
    from .ingestion.flyer_source import FlyerSource
    from .ingestion.pipeline import run_ingestion
    if shutil.which("codex") is None:
        raise RuntimeError("codex CLI nao encontrado no PATH")
    source = FlyerSource(FLYERS_DIR, CodexExtractor(), reference=date.today())
    run_ingestion(session, source, reference=date.today(), label="flyers")
    session.commit()
    move_all(source.processed_paths, FLYERS_DIR / "processed")
    move_all(source.failed_paths, FLYERS_DIR / "failed")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--bairro")
    g.add_argument("--center", help="lat,lng")
    ap.add_argument("--km", type=float, default=DEFAULT_KM)
    ap.add_argument("--sweep-id", type=int, default=None, help="registro criado pela API")
    args = ap.parse_args(argv)
    if args.sweep_id is None and not (args.bairro or args.center):
        ap.error("--bairro ou --center e obrigatorio (a menos que --sweep-id seja passado)")

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
                stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
                if running.started_at < stale_cutoff:
                    # WHY (B3): o processo pode morrer sem tocar o banco (kill,
                    # queda de energia); staleness e a valvula de escape sem
                    # precisar de SQL manual pra destravar.
                    running.status = "error"
                    running.error = "run abandonado (stale > 6h)"
                    running.finished_at = datetime.now(timezone.utc)
                    session.commit()
                else:
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

        pw = context = None
        try:
            from .ingestion.instagram_source import open_context
            pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
            run_sweep(session, sweep, inbox=FLYERS_DIR,
                      scrape=_real_scrape_factory(context),
                      extract=lambda: _real_extract(session),
                      delay=lambda: time.sleep(random.uniform(config.IG_DELAY_MIN,
                                                              config.IG_DELAY_MAX)))
        except Exception as exc:  # noqa: BLE001 — marca o sweep, nao deixa running orfao
            # B2: se a excecao veio de erro de DB, a sessao pode estar numa
            # transacao falha — sem rollback, o commit abaixo tambem estoura.
            session.rollback()
            sweep.status = "error"
            sweep.error = str(exc)[:500]
            sweep.finished_at = datetime.now(timezone.utc)
            session.commit()
            raise
        finally:
            # B1: open_context agora roda DENTRO do try — se o launch do
            # Playwright falhar, context fica None e nao tentamos fechar nada
            # (antes disso rodava fora do try e um sweep 'running' ficava orfao).
            if context is not None:
                context.close()
                pw.stop()
        d = sweep.diff or {}
        print(f"sweep #{sweep.id} {sweep.status}: +{d.get('novas_festas', 0)} festas, "
              f"venues com pin novo: {d.get('venues_com_pin_novo', [])}")


if __name__ == "__main__":
    main()
