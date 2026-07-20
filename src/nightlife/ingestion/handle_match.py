# src/nightlife/ingestion/handle_match.py
"""Decide attach/review/reject para o handle de IG achado via busca (Ciclo E-2b).

PURO: sem rede, sem DB. O risco central e anti-envenenamento — anexar um handle
ERRADO em venue.instagram contamina os detectores a jusante (spec E-2b). Por
isso a barra pro auto-attach e alta: exige nome forte + um confirmador
independente (URL do bio == site do venue, verificado, ou categoria+local).
Tudo o que nao bate um desses confirmadores vai pra review, nao attach.
"""
from __future__ import annotations

from dataclasses import dataclass

from nightlife.domain.matching import name_similarity
from nightlife.domain.nightlife_relevance import is_platform_handle
from nightlife.extraction.social import canonical_handle
from nightlife.ingestion.ig_search import SearchResult

NAME_FLOOR = 0.6      # shortlist threshold
STRONG_NAME = 0.8     # strong name match for attach
_NIGHTLIFE_CAT = ("night", "club", "bar", "music", "danc", "entertainment", "lounge", "casa noturna", "boate")

_SP_TOKENS = ("sao paulo", "são paulo", " sp ", "-sp", "/sp")


@dataclass(frozen=True)
class ProfileSignals:
    handle: str
    bio_link: str | None       # external link in the profile bio
    category: str | None       # IG business category, e.g. "Nightclub", "Bar"
    bio_text: str | None       # the bio text
    is_verified: bool
    follower_count: int | None


@dataclass(frozen=True)
class MatchDecision:
    action: str                # "attach" | "review" | "reject"
    handle: str
    reason: str                # human-readable which rule fired


def norm_url(u: str | None) -> str:
    """Normaliza uma URL pra comparacao: sem esquema, sem www., sem query/fragment,
    sem barra final, lowercase. `norm_url(None) == norm_url("") == ""`."""
    if not u:
        return ""
    s = u.strip().lower()
    if s.startswith("https://"):
        s = s[len("https://"):]
    elif s.startswith("http://"):
        s = s[len("http://"):]
    if s.startswith("www."):
        s = s[len("www."):]
    for sep in ("?", "#"):
        idx = s.find(sep)
        if idx != -1:
            s = s[:idx]
    s = s.rstrip("/")
    return s.strip()


def shortlist(venue_name: str, results: list[SearchResult], *, floor: float = NAME_FLOOR) -> list[SearchResult]:
    """Filtra `results` pelo piso de similaridade de nome (fallback pro username
    quando full_name e fraco/vazio) e ordena por score desc, verificado primeiro
    em empate."""
    scored: list[tuple[float, SearchResult]] = []
    for r in results:
        score = max(name_similarity(venue_name, r.full_name), name_similarity(venue_name, r.username))
        if score >= floor:
            scored.append((score, r))
    scored.sort(key=lambda pair: (-pair[0], not pair[1].is_verified))
    return [r for _, r in scored]


def decide(*, venue_name: str, venue_website: str | None, venue_neighborhood: str | None,
           best: SearchResult, signals: ProfileSignals) -> MatchDecision:
    canon = canonical_handle(best.username)
    if canon is None:
        return MatchDecision("reject", best.username, "handle invalido/nao-perfil")
    if is_platform_handle(canon):
        return MatchDecision("reject", canon, "handle de plataforma/agregador")

    sim = name_similarity(venue_name, best.full_name or best.username)

    # definitivo: bio_link aponta pro mesmo site do venue — a URL prova a
    # identidade por si so, nao exige nome forte.
    if venue_website and signals.bio_link:
        site = norm_url(venue_website)
        link = norm_url(signals.bio_link)
        if link and link == site:
            return MatchDecision("attach", canon, f"bio_link == site do venue ({link})")

    if signals.is_verified and sim >= STRONG_NAME:
        return MatchDecision("attach", canon, f"perfil verificado + nome forte (sim={sim:.2f})")

    if (signals.category is not None
            and any(tok in signals.category.lower() for tok in _NIGHTLIFE_CAT)
            and sim >= STRONG_NAME
            and signals.bio_text is not None):
        bio_lower = signals.bio_text.lower()
        neighborhood_match = bool(venue_neighborhood) and venue_neighborhood.lower() in bio_lower
        sp_match = any(tok in (" " + bio_lower + " ") for tok in _SP_TOKENS)
        if neighborhood_match or sp_match:
            return MatchDecision("attach", canon, "categoria nightlife + local na bio + nome forte")

    return MatchDecision(
        "review", canon,
        f"sem confirmador forte (sim={sim:.2f}, verificado={signals.is_verified}, bio_link!=site)",
    )
