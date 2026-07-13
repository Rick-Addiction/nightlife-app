# src/nightlife/follow_venues.py
"""Segue os venues da fila pela burner aquecida (Ciclo E-3). Ramp-up lento.
Uso: .venv/Scripts/python -m nightlife.follow_venues"""
from __future__ import annotations

import random
import re
import time

from . import config
from .db import SessionLocal
from .ingestion.follow_source import run_follows
from .ingestion.instagram_source import open_context
from .persistence.ig_state import follow_queue


class CheckpointDetected(Exception):
    pass


_FOLLOW_LABELS = ("Seguir", "Follow")
# "ja seguindo" por regex-CONTENDO: o nome acessivel do botao "Seguindo" difere
# do texto visivel (o IG mete estrutura/texto oculto dentro), entao exact=True
# nao casa. Confirmado no smoke (perfil ja-seguido do @blitzhaus). "Seguir" NAO
# e substring de "Seguindo", entao a ordem (already-first) nao da falso-positivo.
_ALREADY_RE = re.compile(r"Seguindo|Following|Solicitado|Requested", re.IGNORECASE)


def _playwright_follow_factory(context):
    def _follow(handle: str) -> None:
        page = context.new_page()
        try:
            page.goto(f"https://www.instagram.com/{handle}/",
                      wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(1500)
            if "challenge" in page.url or "/accounts/suspended" in page.url:
                raise CheckpointDetected(page.url)
            if page.get_by_role("button", name=_ALREADY_RE).count():
                return  # ja seguindo/solicitado — sucesso sem clicar
            for label in _FOLLOW_LABELS:
                btn = page.get_by_role("button", name=label, exact=True)
                if btn.count():
                    btn.first.click(timeout=8000)
                    page.wait_for_timeout(1500)
                    return
            # nenhum botao casou: NAO marca followed_at (seria estado corrompido —
            # fila drenada sem seguir ninguem se o seletor exact estiver errado no
            # smoke). Levanta => run_follows trata como falha isolada, pula, retenta.
            raise RuntimeError(f"nenhum botao Seguir/Seguindo em @{handle} (seletor?)")
        finally:
            page.close()
    return _follow


def main() -> None:
    with SessionLocal() as session:
        handles = follow_queue(session, cap=config.IG_MAX_FOLLOWS_PER_RUN)
        if not handles:
            print("nada a seguir (todos os venues com handle ja seguidos).")
            return
        pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
        try:
            n = run_follows(
                session, handles,
                follow=_playwright_follow_factory(context),
                delay=lambda: time.sleep(random.uniform(config.IG_DELAY_MIN,
                                                        config.IG_DELAY_MAX)),
                checkpoint_exc=CheckpointDetected)
        finally:
            context.close()
            pw.stop()
        print(f"segui {n}/{len(handles)} (auto-pausa no 1o checkpoint).")


if __name__ == "__main__":
    main()
