# src/nightlife/persistence/_utils.py
from __future__ import annotations

import hashlib


def payload_hash(payload: str) -> str:
    """SHA-256 hex do payload bruto da fonte (evidencia)."""
    return hashlib.sha256((payload or "").encode("utf-8")).hexdigest()
