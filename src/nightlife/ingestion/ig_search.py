"""Parser puro para as respostas dos endpoints de busca/perfil do Instagram
(web/search/topsearch/ e api/v1/users/web_profile_info/).

Nao faz rede nesses parsers: apenas recebem o payload (dict) ja decodificado.
As cascas de rede (`playwright_search`, `fetch_profile_signals`) reusam o
context autenticado da burner (ver instagram_source.open_context), igual ao
probe_ig_search — navegam 1x pra home antes de chamar context.request.get.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

# X-IG-App-ID e o app id publico da web do IG (confirmado no probe real);
# sem ele o topsearch/web_profile_info devolvem 401/403 mesmo com cookies ok.
IG_HEADERS = {
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
}

_TOPSEARCH_URL = "https://www.instagram.com/web/search/topsearch/?context=blended&query={q}"
_PROFILE_URL = "https://www.instagram.com/api/v1/users/web_profile_info/?username={h}"


@dataclass(frozen=True)
class SearchResult:
    username: str
    full_name: str
    is_verified: bool
    is_private: bool


@dataclass(frozen=True)
class ProfileSignals:
    handle: str
    bio_link: str | None       # external link in the profile bio
    category: str | None       # IG business category, e.g. "Nightclub", "Bar"
    bio_text: str | None       # the bio text
    is_verified: bool
    follower_count: int | None


def parse_search_results(payload: dict) -> list[SearchResult]:
    if not isinstance(payload, dict):
        return []

    users = payload.get("users") or []
    if not isinstance(users, list):
        return []

    results: list[SearchResult] = []
    for entry in users:
        if not isinstance(entry, dict):
            continue
        user = entry.get("user")
        if not isinstance(user, dict):
            continue
        username = user.get("username")
        if not username:
            continue
        results.append(SearchResult(
            username=username,
            full_name=user.get("full_name") or "",
            is_verified=bool(user.get("is_verified")),
            is_private=bool(user.get("is_private")),
        ))
    return results


def _bio_link_of(user: dict) -> str | None:
    """bio_links[0].url (link limpo, NAO o lynx_url de redirect); se ausente/
    vazio cai pro external_url; senao None."""
    bio_links = user.get("bio_links")
    if isinstance(bio_links, list) and bio_links:
        first = bio_links[0]
        if isinstance(first, dict):
            url = first.get("url")
            if url:
                return url
    external_url = user.get("external_url")
    return external_url or None


def parse_profile_signals(handle: str, payload: dict) -> "ProfileSignals":
    """JSON do web_profile_info/ -> ProfileSignals. PURO, nunca estoura:
    payload ausente/mal-formado -> campos None/False (categoria e nome de
    negocio costumam vir None mesmo em perfis validos — e esperado)."""
    user = {}
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            candidate = data.get("user")
            if isinstance(candidate, dict):
                user = candidate

    category = user.get("category_name") or user.get("business_category_name") or None
    follower_count = None
    edge = user.get("edge_followed_by")
    if isinstance(edge, dict):
        count = edge.get("count")
        if isinstance(count, int):
            follower_count = count

    return ProfileSignals(
        handle=handle,
        bio_link=_bio_link_of(user),
        category=category,
        bio_text=user.get("biography") or None,
        is_verified=bool(user.get("is_verified")),
        follower_count=follower_count,
    )


def playwright_search(context, query: str) -> list[SearchResult]:
    """Busca `query` no topsearch do IG usando a sessao autenticada da burner.

    Precisa passar pela home logada 1x pra os cookies/headers valerem (igual
    ao probe_ig_search); em qualquer falha (status/CT ruins) devolve []."""
    page = context.new_page()
    try:
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        url = _TOPSEARCH_URL.format(q=quote(query))
        resp = context.request.get(url, headers=IG_HEADERS)
        ct = resp.headers.get("content-type", "")
        if not resp.ok or "application/json" not in ct:
            return []
        return parse_search_results(resp.json())
    finally:
        page.close()


def fetch_profile_signals(context, handle: str) -> ProfileSignals | None:
    """Busca o perfil de `handle` (web_profile_info/) e extrai os sinais.

    Mesmo padrao de navegar 1x pra home antes do request; falha de rede/shape
    devolve None (o chamador decide o que fazer — nao anexa handle sem sinal)."""
    page = context.new_page()
    try:
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        url = _PROFILE_URL.format(h=quote(handle))
        resp = context.request.get(url, headers=IG_HEADERS)
        ct = resp.headers.get("content-type", "")
        if not resp.ok or "application/json" not in ct:
            return None
        return parse_profile_signals(handle, resp.json())
    finally:
        page.close()
