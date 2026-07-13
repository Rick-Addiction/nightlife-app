"""Bootstrap do Ciclo E-3: segue um lote pequeno de venues pela burner pra
desbloquear o probe do feed (o feed so tem post real se a conta seguir contas).
Quentes primeiro, intervalo 30s-2min, AUTO-PAUSA no 1o checkpoint. Idempotente:
pula quem ja mostra 'Seguindo' (nao persiste estado — o modulo real do plano faz).

Uso: BOOTSTRAP_FOLLOW_CAP=10 .venv/Scripts/python -m nightlife.bootstrap_follows
"""
from __future__ import annotations

import os
import random
import time

from sqlalchemy import select

from . import config
from .db import SessionLocal
from .ingestion.instagram_source import open_context
from .models import Venue
from .persistence.ig_state import _hot_handles

CAP = int(os.environ.get("BOOTSTRAP_FOLLOW_CAP", "10"))
_FOLLOW_LABELS = ("Seguir", "Follow")
_ALREADY = ("Seguindo", "Following", "Solicitado", "Requested")


class CheckpointDetected(Exception):
    pass


def _pick_handles(session) -> list[str]:
    hot = _hot_handles(session)
    rows = session.scalars(
        select(Venue).where(Venue.instagram.is_not(None)).order_by(Venue.id)).all()
    seen: set[str] = set()
    ranked: list[tuple[int, str]] = []
    for v in rows:
        h = v.instagram
        if h in seen:
            continue
        seen.add(h)
        ranked.append((0 if h in hot else 1, h))
    ranked.sort(key=lambda t: t[0])
    return [h for _, h in ranked][:CAP]


def _follow(context, handle: str) -> str:
    """Devolve 'seguiu' | 'ja' | 'sem_botao'. Levanta CheckpointDetected."""
    page = context.new_page()
    try:
        page.goto(f"https://www.instagram.com/{handle}/",
                  wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        if "challenge" in page.url or "/accounts/suspended" in page.url:
            raise CheckpointDetected(page.url)
        for label in _ALREADY:
            if page.get_by_role("button", name=label, exact=True).count():
                return "ja"
        for label in _FOLLOW_LABELS:
            btn = page.get_by_role("button", name=label, exact=True)
            if btn.count():
                btn.first.click(timeout=8000)
                page.wait_for_timeout(2000)
                return "seguiu"
        return "sem_botao"
    finally:
        page.close()


def main() -> None:
    with SessionLocal() as session:
        handles = _pick_handles(session)
    if not handles:
        print("nenhum venue com handle.")
        return
    print(f"vou tentar seguir {len(handles)} (quentes primeiro): {handles}")
    pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
    seguiu = 0
    try:
        for i, handle in enumerate(handles):
            try:
                r = _follow(context, handle)
            except CheckpointDetected as exc:
                print(f"CHECKPOINT em @{handle} ({exc}) — auto-pausa.")
                break
            except Exception as exc:  # noqa: BLE001 — perfil sumiu/privado etc.
                print(f"@{handle}: erro ({str(exc)[:80]}) — pula.")
                continue
            print(f"@{handle}: {r}")
            if r == "seguiu":
                seguiu += 1
            if i < len(handles) - 1:
                wait = random.uniform(30, 120)
                print(f"   ...aguardando {wait:.0f}s")
                time.sleep(wait)
    finally:
        context.close()
        pw.stop()
    print(f"pronto: segui {seguiu} novos.")


if __name__ == "__main__":
    main()
