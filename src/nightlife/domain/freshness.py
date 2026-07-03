# src/nightlife/domain/freshness.py
from __future__ import annotations

from datetime import datetime

_FULL_DAYS = 30.0    # ate aqui, frescor pleno
_FLOOR_DAYS = 180.0  # daqui em diante, piso
_FLOOR = 0.5


def freshness_factor(last_seen_at: datetime, now: datetime) -> float:
    """Fator multiplicativo de frescor: 1.0 ate 30 dias sem reconfirmacao,
    decai linearmente ate 0.5 aos 180 dias, e fica no piso 0.5.
    Aplicado na LEITURA (effective_confidence) — nightlife e efemero, mas
    registro antigo ainda vale metade, nunca zero."""
    age_days = max(0.0, (now - last_seen_at).total_seconds() / 86400.0)
    if age_days <= _FULL_DAYS:
        return 1.0
    if age_days >= _FLOOR_DAYS:
        return _FLOOR
    return 1.0 - (1.0 - _FLOOR) * (age_days - _FULL_DAYS) / (_FLOOR_DAYS - _FULL_DAYS)
