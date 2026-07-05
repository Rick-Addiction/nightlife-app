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


def open_context(user_data_dir: Path, *, headful: bool):
    """Abre um persistent context do chromium com a sessao da burner."""
    from playwright.sync_api import sync_playwright  # lazy: so quando de fato scrapeia
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        str(user_data_dir), headless=not headful,
    )
    return pw, context


def playwright_fetch_posts(context, handle: str) -> list[IgPost]:
    """Navega ao perfil e captura as respostas JSON do IG; parse_profile_posts
    (puro, testado) filtra a que tem o timeline (spec §6.3).

    BRITTLE por natureza (o IG ofusca/muda): calibrar no smoke. Capturamos todo
    JSON e delegamos ao parse — o contrato estavel e parse_profile_posts."""
    page = context.new_page()
    captured: list[dict] = []

    def _on_response(resp):
        if "application/json" not in resp.headers.get("content-type", ""):
            return
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001 — nem toda resposta JSON e util
            return
        if isinstance(data, dict):
            captured.append(data)  # parse_profile_posts acha a que tem timeline

    page.on("response", _on_response)
    page.goto(f"https://www.instagram.com/{handle}/", wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(2500)
    posts: list[IgPost] = []
    for data in captured:
        posts = parse_profile_posts(data)
        if posts:
            break
    page.close()
    return posts


def playwright_download(context, post: IgPost, dest: Path) -> Path:
    """Baixa a imagem do post usando a sessao autenticada (cookies do context)."""
    resp = context.request.get(post.image_url, timeout=30000)
    dest.write_bytes(resp.body())
    return dest
