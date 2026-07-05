# src/nightlife/ingestion/instagram_source.py
"""Scraper de Instagram (spec §6). O PARSE do JSON do IG e puro e testavel;
a navegacao Playwright fica numa casca injetavel (Task 9), como o CodexExtractor."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_log = logging.getLogger(__name__)


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


@dataclass
class ScrapeConfig:
    inbox: Path
    cap: int = 6


@dataclass
class ScrapeResult:
    handle: str
    last_shortcode: str | None
    downloaded: int


def _ext_from_url(url: str) -> str:
    for e in (".jpg", ".jpeg", ".png", ".webp"):
        if e in url.lower():
            return e
    return ".jpg"


def permalink_of(shortcode: str) -> str:
    return f"https://www.instagram.com/p/{shortcode}/"


def scrape_handle(
    handle: str, *, last_shortcode: str | None,
    fetch_posts: Callable[[str], list[IgPost]],
    download: Callable[[IgPost, Path], Path],
    config: ScrapeConfig,
) -> ScrapeResult:
    """Varre um handle: baixa imagem + sidecar dos posts novos no inbox.

    `fetch_posts` (navegador) e `download` (baixador) sao injetados — a casca
    Playwright real vem na Task 9; aqui a logica e testada com fakes."""
    config.inbox.mkdir(parents=True, exist_ok=True)
    posts = fetch_posts(handle)
    fresh = new_posts(posts, last_shortcode=last_shortcode, cap=config.cap)
    downloaded = 0
    for post in fresh:
        image_path = config.inbox / f"{post.shortcode}{_ext_from_url(post.image_url)}"
        try:
            download(post, image_path)
        except Exception as exc:  # noqa: BLE001 — pula o post, segue os outros
            _log.warning("download de %s falhou: %s", post.shortcode, exc)
            continue
        sidecar = config.inbox / f"{post.shortcode}.json"
        sidecar.write_text(json.dumps({
            "handle": handle,
            "permalink": permalink_of(post.shortcode),
            "caption": post.caption,
            "taken_at": post.taken_at,
        }, ensure_ascii=False), encoding="utf-8")
        downloaded += 1
    # cursor novo = o post mais recente visto (posts[0]); se nao havia posts, mantem
    new_cursor = posts[0].shortcode if posts else last_shortcode
    return ScrapeResult(handle=handle, last_shortcode=new_cursor, downloaded=downloaded)
