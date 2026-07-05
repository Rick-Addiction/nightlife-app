# src/nightlife/domain/nightlife_relevance.py
"""Relevancia de venue: 'isto e vida noturna?' (spec §3). Puro, sem DB.

blocked (buffet/festa-infantil, nunca) tem precedencia; relevant (nightclub, ou
com evento, ou monitorado); dormant (o resto — events_venue/sem-cat sem evento)."""
from __future__ import annotations

import unicodedata


def _norm(s: str | None) -> str:
    """lowercase + sem acento, p/ casar palavras robustamente."""
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


_BUFFET_KEYWORDS = (
    "buffet", "bufe", "infantil", "kids", "salao de festa", "aniversario",
    "festa infantil",
)


def is_buffet_name(name: str | None) -> bool:
    n = _norm(name)
    return any(kw in n for kw in _BUFFET_KEYWORDS)


_PLATFORM_HANDLES = frozenset({
    "sympla", "ifood", "ifoodbrasil", "facebook", "whatsapp", "instagram",
    "youtube", "tiktok", "linktr", "linktree",
})


def is_platform_handle(handle: str | None) -> bool:
    return (handle or "").lower() in _PLATFORM_HANDLES


def venue_relevance(name: str | None, category: str | None,
                    has_events: bool, is_monitored: bool) -> str:
    """'blocked' | 'relevant' | 'dormant'. blocked tem precedencia sobre tudo."""
    if is_buffet_name(name):
        return "blocked"
    if category == "nightclub" or has_events or is_monitored:
        return "relevant"
    return "dormant"
