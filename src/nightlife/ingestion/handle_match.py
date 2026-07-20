# src/nightlife/ingestion/handle_match.py
"""Decide attach/review/reject para o handle de IG achado via busca (Ciclo E-2b).

PURO: sem rede, sem DB. O risco central e anti-envenenamento — anexar um handle
ERRADO em venue.instagram contamina os detectores a jusante (spec E-2b). Por
isso a barra pro auto-attach e alta: exige nome forte + um confirmador
independente (URL do bio == site do venue no dominio proprio, OU verificado/
categoria+nome-forte com uma ANCORA de localidade/identidade real — bairro/SP/
rua do venue na bio — OU nome muito forte + endereco na bio). Um perfil
verificado ou com categoria nightlife SEM nenhuma ancora local pode ser um
homonimo nacional/generico: isso vai pra review, nunca attach. Perfil privado
nunca e a pagina publica de um venue: sempre review. Tudo o que nao bate um
confirmador vai pra review, nao attach.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from nightlife.domain.matching import name_similarity
from nightlife.domain.nightlife_relevance import is_platform_handle
from nightlife.extraction.freetext import _is_generic_link
from nightlife.extraction.social import canonical_handle
from nightlife.ingestion.ig_search import ProfileSignals, SearchResult

NAME_FLOOR = 0.6          # shortlist threshold
STRONG_NAME = 0.8         # strong name match for attach
VERY_STRONG_NAME = 0.9    # very strong name match (confirmer 4: address in bio)
_NIGHTLIFE_CAT = ("night", "club", "bar", "music", "danc", "entertainment", "lounge", "casa noturna", "boate")

# _SP tokens matched by WORD BOUNDARY over accent-stripped bio (M1 fix)
_SP_RE = re.compile(r"\b(sao paulo|sp)\b")
_STREET_PREFIX = re.compile(r"^(r\.?|rua|av\.?|avenida|al\.?|alameda|pra[cç]a|travessa|estr\.?|estrada)\s+")


@dataclass(frozen=True)
class MatchDecision:
    action: str                # "attach" | "review" | "reject"
    handle: str
    reason: str                # human-readable which rule fired


def _norm_txt(s: str | None) -> str:
    """lowercase + sem acento, p/ casar palavras robustamente."""
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower())
                   if unicodedata.category(c) != "Mn")


def _street_name(address: str | None) -> str | None:
    """Nome da rua do endereco do venue, normalizado (sem tipo/numero). Ex.:
    'R. Peixoto Gomide, 73' -> 'peixoto gomide'. None se curto/ausente."""
    if not address:
        return None
    first = _norm_txt(address.split(",")[0]).strip()
    first = _STREET_PREFIX.sub("", first).strip()
    return first if len(first) >= 5 else None


def _place_signal(signals: ProfileSignals, venue_neighborhood: str | None, venue_address: str | None) -> bool:
    """A bio ancora o perfil em SP/no bairro/na rua do venue? (prova de que e
    ESTE venue local, nao um homonimo nacional)."""
    if not signals.bio_text:
        return False
    bio = _norm_txt(signals.bio_text)
    if venue_neighborhood and _norm_txt(venue_neighborhood) in bio:
        return True
    if _SP_RE.search(bio):
        return True
    street = _street_name(venue_address)
    return bool(street and street in bio)


def norm_url(u: str | None, *, keep_query: bool = False) -> str:
    """Normaliza uma URL pra comparacao: sem esquema, sem www., sem barra
    final, lowercase. Por padrao tambem remove query/fragment; com
    `keep_query=True` a query/fragment sao preservados (usado pelo confirmador
    definitivo de bio_link==site, pra nao colidir URLs com `?id=` diferente).
    `norm_url(None) == norm_url("") == ""`."""
    if not u:
        return ""
    s = u.strip().lower()
    if s.startswith("https://"):
        s = s[len("https://"):]
    elif s.startswith("http://"):
        s = s[len("http://"):]
    if s.startswith("www."):
        s = s[len("www."):]
    if not keep_query:
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
           best: SearchResult, signals: ProfileSignals,
           venue_address: str | None = None) -> MatchDecision:
    canon = canonical_handle(best.username)
    if canon is None:
        return MatchDecision("reject", best.username, "handle invalido/nao-perfil")
    if is_platform_handle(canon):
        return MatchDecision("reject", canon, "handle de plataforma/agregador")
    if best.is_private:  # M2: perfil privado nao e pagina publica de venue
        return MatchDecision("review", canon, "perfil privado — nao e pagina publica de venue")

    sim = name_similarity(venue_name, best.full_name or best.username)
    place = _place_signal(signals, venue_neighborhood, venue_address)

    # 1. definitivo: bio_link == site do venue, no dominio PROPRIO (nao plataforma
    #    compartilhada) e com query preservada (evita colisao por ?id diferente).
    if venue_website and signals.bio_link and not _is_generic_link(signals.bio_link):
        site = norm_url(venue_website, keep_query=True)
        link = norm_url(signals.bio_link, keep_query=True)
        if link and link == site:
            return MatchDecision("attach", canon, f"bio_link == site do venue ({link})")

    # 2. verificado + nome forte + LOCAL (verificacao prova autenticidade; local
    #    prova que e ESTE venue de SP, nao homonimo nacional). [C1 fix: exige place]
    if signals.is_verified and sim >= STRONG_NAME and place:
        return MatchDecision("attach", canon, f"verificado + nome forte + local na bio (sim={sim:.2f})")

    # 3. categoria nightlife + nome forte + LOCAL
    if (signals.category is not None
            and any(tok in signals.category.lower() for tok in _NIGHTLIFE_CAT)
            and sim >= STRONG_NAME and place):
        return MatchDecision("attach", canon, "categoria nightlife + nome forte + local na bio")

    # 4. nome MUITO forte + endereco na bio (identidade fisica — a rua do venue
    #    aparece na bio; um homonimo nao teria o mesmo endereco).
    street = _street_name(venue_address)
    if sim >= VERY_STRONG_NAME and street and signals.bio_text and street in _norm_txt(signals.bio_text):
        return MatchDecision("attach", canon, "nome muito forte + endereco na bio")

    return MatchDecision(
        "review", canon,
        f"sem confirmador forte (sim={sim:.2f}, verificado={signals.is_verified}, place={place}, bio_link!=site)",
    )
