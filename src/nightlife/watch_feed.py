# src/nightlife/watch_feed.py
"""Detector do feed 'Seguindo' (Ciclo E-3): le o feed, acha posts novos por
handle (cursor), baixa so esses posts e roda o intérprete do E-1. So age na
janela noturna. Uso (agendado 45min): .venv/Scripts/python -m nightlife.watch_feed"""
from __future__ import annotations

from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import select

from . import config
from .db import SessionLocal
from .ingestion.feed_source import FeedItem, new_since_cursor, playwright_fetch_feed
from .ingestion.instagram_source import open_context, permalink_of
from .models import IgProfileState, Venue
from .persistence.ig_state import get_or_create_state

_SP_TZ = ZoneInfo("America/Sao_Paulo")
FLYERS_DIR = Path("flyers")


def in_window(now: dtime, *, start: int, end: int) -> bool:
    """Janela que cruza a meia-noite (start=10, end=2 => 10h ate 02h)."""
    if start <= end:
        return start <= now.hour < end
    return now.hour >= start or now.hour < end


def detect_and_fetch(session, items: list[FeedItem], *,
                     fetch: Callable[[str, str], None],
                     cursor_by_handle: dict[str, str]) -> int:
    """Baixa os posts novos e avanca o cursor por handle pro shortcode do topo."""
    novos = new_since_cursor(items, cursor_by_handle)
    # so venues que temos no catalogo (o feed pode ter contas seguidas a mais)
    known = set(session.scalars(select(Venue.instagram)
                                .where(Venue.instagram.is_not(None))).all())
    top_by_handle: dict[str, str] = {}
    n = 0
    for it in novos:
        if it.handle not in known:
            continue
        fetch(it.handle, it.shortcode)
        top_by_handle.setdefault(it.handle, it.shortcode)  # 1o = mais novo
        n += 1
    for handle, top in top_by_handle.items():
        get_or_create_state(session, handle).last_shortcode = top
    session.commit()
    return n


def _real_fetch_factory(context):
    from .ingestion.instagram_source import IgPost, playwright_download
    import json as _json

    def _fetch(handle: str, shortcode: str) -> None:
        # baixa a imagem do permalink e grava sidecar (mesmo contrato do ingest_ig)
        FLYERS_DIR.mkdir(exist_ok=True)
        page = context.new_page()
        try:
            page.goto(permalink_of(shortcode), wait_until="networkidle", timeout=45000)
            img_url = page.locator('meta[property="og:image"]').first.get_attribute(
                "content", timeout=5000)
            caption = page.locator('meta[property="og:title"]').first.get_attribute(
                "content", timeout=5000)
        finally:
            page.close()
        if not img_url:
            return
        post = IgPost(shortcode=shortcode, image_url=img_url, caption=caption, taken_at=None)
        dest = FLYERS_DIR / f"{shortcode}.jpg"
        playwright_download(context, post, dest)
        (FLYERS_DIR / f"{shortcode}.json").write_text(
            _json.dumps({"handle": handle, "caption": caption,
                         "permalink": permalink_of(shortcode)}, ensure_ascii=False),
            encoding="utf-8")
    return _fetch


def main() -> None:
    now = datetime.now(_SP_TZ)
    if not in_window(now.time(), start=config.FEED_WINDOW_START_HOUR,
                     end=config.FEED_WINDOW_END_HOUR):
        print(f"fora da janela ({now:%H:%M} SP) — nada a fazer.")
        return
    with SessionLocal() as session:
        cursor = {st.handle: st.last_shortcode for st in
                  session.scalars(select(IgProfileState)) if st.last_shortcode}
        pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
        try:
            items = playwright_fetch_feed(context)
            n = detect_and_fetch(session, items,
                                 fetch=_real_fetch_factory(context),
                                 cursor_by_handle=cursor)
        finally:
            context.close()
            pw.stop()
        print(f"feed: {len(items)} itens, {n} posts novos baixados pro inbox.")
    # extrai os posts novos pelo intérprete do E-1 (mesmo inbox)
    if n:
        from .ingest_flyers import main as _extract
        _extract()


if __name__ == "__main__":
    main()
