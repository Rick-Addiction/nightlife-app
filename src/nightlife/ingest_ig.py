# src/nightlife/ingest_ig.py
"""Varre os perfis de IG descobertos, baixando flyers recentes pro inbox flyers/.

Uso (apos ig_login): .venv/Scripts/python -m nightlife.ingest_ig
Ritmo conservador (spec §6): headful, delays humanos, caps de config."""
from __future__ import annotations

import random
import time
from pathlib import Path

from . import config
from .db import SessionLocal
from .ingestion.instagram_source import (
    ScrapeConfig, open_context, playwright_download, playwright_fetch_posts, scrape_handle,
)
from .persistence.ig_state import (
    get_or_create_state, record_failure, record_success, record_venue_activity,
    scrape_queue,
)

FLYERS_DIR = Path("flyers")


def main() -> None:
    FLYERS_DIR.mkdir(exist_ok=True)
    with SessionLocal() as session:
        handles = scrape_queue(session, cap=config.IG_MAX_PROFILES_PER_RUN,
                               pause_threshold=config.IG_FAILURE_PAUSE_THRESHOLD)
        if not handles:
            print("nenhum handle a varrer (rode discover_handles primeiro).")
            return
        pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
        total = 0
        try:
            for handle in handles:
                st = get_or_create_state(session, handle)
                cap = (config.IG_MAX_POSTS_FIRST_SWEEP if st.last_shortcode is None
                       else config.IG_MAX_POSTS_INCREMENTAL)
                cfg = ScrapeConfig(inbox=FLYERS_DIR, cap=cap)
                try:
                    result = scrape_handle(
                        handle, last_shortcode=st.last_shortcode,
                        fetch_posts=lambda h: playwright_fetch_posts(context, h),
                        download=lambda p, d: playwright_download(context, p, d),
                        config=cfg,
                    )
                    record_success(st, result.last_shortcode)
                    record_venue_activity(session, handle, result.latest_post_at)
                    total += result.downloaded
                    print(f"@{handle}: {result.downloaded} novas")
                except Exception as exc:  # noqa: BLE001 — falha isolada por handle
                    record_failure(st)
                    print(f"@{handle}: FALHA ({exc}) — falhas={st.consecutive_failures}")
                session.commit()
                time.sleep(random.uniform(config.IG_DELAY_MIN, config.IG_DELAY_MAX))
        finally:
            context.close()
            pw.stop()
        print(f"total baixado: {total} imagens em {FLYERS_DIR}/ "
              f"(rode ingest_flyers para extrair)")


if __name__ == "__main__":
    main()
