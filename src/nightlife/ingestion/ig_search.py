"""Parser puro para a resposta do endpoint web/search/topsearch/ do Instagram.

Nao faz rede: apenas recebe o payload (dict) ja decodificado e devolve os
resultados de usuario, na ordem em que aparecem em `payload["users"]`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    username: str
    full_name: str
    is_verified: bool
    is_private: bool


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
