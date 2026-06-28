# src/nightlife/extraction/freetext.py
from __future__ import annotations

import re
from datetime import date

from ..domain.dates_ptbr import parse_ptbr_datetime
from .base import ExtractedEvent


def extract_freetext_deterministic(
    text: str, *, reference: date, source_url: str | None = None
) -> ExtractedEvent:
    ev = ExtractedEvent(source_url=source_url, raw={"text": text})

    pd = parse_ptbr_datetime(text, reference=reference)
    ev.starts_at = pd.dt
    ev.starts_at_raw = pd.matched
    if pd.dt is not None:
        ev.field_confidence["starts_at"] = 0.5 if pd.ambiguous else 0.9

    for line in text.splitlines():
        if line.strip():
            ev.name = line.strip()
            break

    m = re.search(r"https?://\S+", text)
    if m:
        # tira pontuacao de fim (ex.: "...mamba)." ) para nao corromper o
        # ticket_url, que e usado como chave de deduplicacao por igualdade.
        ev.ticket_url = m.group(0).rstrip(".,;:!?)]}>\"'")

    return ev
