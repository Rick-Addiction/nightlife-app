# src/nightlife/domain/nightlife_relevance.py
"""Relevancia de venue: 'isto e vida noturna?' (spec §3). Puro, sem DB.

v2 (Ciclo A): blocked (buffet/festa-infantil, ou fechado em definitivo pelo
Google) tem precedencia; relevant (com evento, ou monitorado, ou nightclub
VIVO — verificado pelo Places, 2+ fontes ou com contato); dormant (o resto,
incluindo nightclub do diretorio do RA sem nenhum sinal de vida)."""
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
                    has_events: bool, is_monitored: bool, *,
                    places_verified: bool = False,
                    business_status: str | None = None,
                    source_count: int = 1,
                    has_contact: bool = False,
                    ig_stale: bool = False) -> str:
    """'blocked' | 'relevant' | 'dormant'. v2 (Ciclo A): nightclub so e relevant
    se VIVO (verificado pelo Places, 2+ fontes ou contato) — o diretorio do RA
    guarda clubes historicos, entao categoria sozinha nao prova existencia.
    blocked (buffet, ou fechado em definitivo pelo Google) tem precedencia."""
    if is_buffet_name(name) or business_status == "CLOSED_PERMANENTLY":
        return "blocked"
    if has_events or is_monitored:
        return "relevant"           # atividade vence sempre
    # IG parado ha 12+ meses: o contato nao prova vida (mas Google OPERATIONAL
    # e atividade continuam valendo)
    alive = places_verified or source_count >= 2 or (has_contact and not ig_stale)
    if category == "nightclub" and alive:
        return "relevant"
    return "dormant"
