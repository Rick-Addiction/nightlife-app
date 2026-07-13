# src/nightlife/ingestion/follow_source.py
"""Nucleo do follow (Ciclo E-3): segue handles um a um, marca followed_at,
AUTO-PAUSA no 1o checkpoint (a acao de escrita mais vigiada — parar cedo protege
a burner). follow/delay injetaveis: teste offline."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from ..persistence.ig_state import get_or_create_state


def run_follows(session: Session, handles: list[str], *, follow: Callable[[str], None],
                delay: Callable[[], None], checkpoint_exc: type[BaseException]) -> int:
    seguidos = 0
    for handle in handles:
        # cria/recupera o state ANTES de tentar seguir: mesmo um checkpoint (ou
        # falha isolada) deixa rastro do handle tentado, so sem followed_at.
        st = get_or_create_state(session, handle)
        try:
            follow(handle)
        except checkpoint_exc:
            break                          # auto-pausa: nao insiste apos challenge
        except Exception:                  # noqa: BLE001 — falha isolada (perfil sumiu etc.)
            continue
        st.followed_at = datetime.now(timezone.utc)
        session.commit()
        seguidos += 1
        delay()
    return seguidos
