# src/nightlife/ingestion/instagram_source.py
"""Scraper de Instagram (spec §6). O PARSE do JSON do IG e puro e testavel;
a navegacao Playwright fica numa casca injetavel (Task 9), como o CodexExtractor."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IgPost:
    shortcode: str
    image_url: str
    caption: str | None
    taken_at: int | None


def _caption_of(node: dict) -> str | None:
    edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
    if edges:
        text = (edges[0].get("node") or {}).get("text")
        return text or None
    return None


def parse_profile_posts(graphql: dict) -> list[IgPost]:
    """JSON GraphQL do perfil -> lista de IgPost (mais recentes primeiro).

    Tolerante a formato ausente/None: devolve [] em vez de estourar (o IG muda
    o shape com frequencia — o fallback e melhor que quebrar o run inteiro)."""
    user = ((graphql.get("data") or {}).get("user")) or {}
    edges = ((user.get("edge_owner_to_timeline_media") or {}).get("edges")) or []
    out: list[IgPost] = []
    for edge in edges:
        node = edge.get("node") or {}
        shortcode = node.get("shortcode")
        image_url = node.get("display_url")
        if not shortcode or not image_url:
            continue
        out.append(IgPost(
            shortcode=shortcode,
            image_url=image_url,
            caption=_caption_of(node),
            taken_at=node.get("taken_at_timestamp"),
        ))
    return out


def new_posts(posts: list[IgPost], *, last_shortcode: str | None, cap: int) -> list[IgPost]:
    """Posts novos desde last_shortcode (para ao encontra-lo), limitado a cap."""
    out: list[IgPost] = []
    for p in posts:
        if last_shortcode is not None and p.shortcode == last_shortcode:
            break
        out.append(p)
        if len(out) >= cap:
            break
    return out
