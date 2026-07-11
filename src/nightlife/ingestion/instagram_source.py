# src/nightlife/ingestion/instagram_source.py
"""Scraper de Instagram (spec §6). O PARSE do JSON do IG e puro e testavel;
a navegacao Playwright fica numa casca injetavel (Task 9), como o PostInterpreter."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_log = logging.getLogger(__name__)

# shortcode vem da rede: sanitiza antes de virar nome de arquivo (evita path
# traversal tipo "../victim/x"). Shortcodes reais do IG sao [A-Za-z0-9_-]{11}.
_VALID_SHORTCODE = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclass
class IgPost:
    shortcode: str
    image_url: str
    caption: str | None
    taken_at: int | None


def _edges(graphql: dict) -> list:
    """Edges do timeline, tolerante aos DOIS shapes que o IG serve (mid-migracao):
    moderno `xdt_api__v1__feed__user_timeline_graphql_connection` e o legado
    `user.edge_owner_to_timeline_media`."""
    data = graphql.get("data") or {}
    conn = data.get("xdt_api__v1__feed__user_timeline_graphql_connection")
    if isinstance(conn, dict):
        return conn.get("edges") or []
    user = data.get("user") or {}
    return (user.get("edge_owner_to_timeline_media") or {}).get("edges") or []


def _shortcode_of(node: dict) -> str | None:
    return node.get("code") or node.get("shortcode")  # moderno: 'code'; legado: 'shortcode'


def _image_of(node: dict) -> str | None:
    iv = node.get("image_versions2")            # moderno: candidates[0] e a maior
    if isinstance(iv, dict):
        cands = iv.get("candidates") or []
        if cands and cands[0].get("url"):
            return cands[0]["url"]
    return node.get("display_url")              # legado


def _caption_of(node: dict) -> str | None:
    cap = node.get("caption")                   # moderno: caption.text (ou None)
    if isinstance(cap, dict):
        return cap.get("text") or None
    edges = (node.get("edge_media_to_caption") or {}).get("edges") or []  # legado
    if edges:
        return ((edges[0].get("node") or {}).get("text")) or None
    return None


def _taken_at_of(node: dict) -> int | None:
    return node.get("taken_at") or node.get("taken_at_timestamp")


def parse_profile_posts(graphql: dict) -> list[IgPost]:
    """JSON do perfil -> lista de IgPost (mais recentes primeiro).

    Tolerante a formato ausente/None: devolve [] em vez de estourar (o IG muda
    o shape com frequencia — o fallback e melhor que quebrar o run inteiro).
    Entende o shape moderno (xdt/v1 feed) e o legado (edge_owner_to_timeline)."""
    if not isinstance(graphql, dict):
        return []
    out: list[IgPost] = []
    for edge in _edges(graphql):
        node = edge.get("node") or {}
        shortcode = _shortcode_of(node)
        image_url = _image_of(node)
        if not shortcode or not image_url or not _VALID_SHORTCODE.fullmatch(shortcode):
            continue
        out.append(IgPost(
            shortcode=shortcode,
            image_url=image_url,
            caption=_caption_of(node),
            taken_at=_taken_at_of(node),
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
    latest_post_at: datetime | None = None


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
    # o timeline e visto em TODA varredura (mesmo incremental sem download):
    # vira o sinal de vida do venue (ig_last_post_at). max(), NAO o primeiro:
    # post FIXADO fica no topo com data antiga e falsearia o sinal
    ts = max((p.taken_at for p in posts if p.taken_at), default=None)
    latest_post_at = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
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
    # cursor so avanca se TODOS os posts novos baixaram; se algum falhou, mantem o
    # cursor antigo p/ re-tentar no proximo run (evita perder flyer por falha
    # transitoria de download). Sem posts novos: marca o topo visto.
    if not fresh:
        new_cursor = posts[0].shortcode if posts else last_shortcode
    elif downloaded == len(fresh):
        new_cursor = fresh[0].shortcode
    else:
        new_cursor = last_shortcode
    return ScrapeResult(handle=handle, last_shortcode=new_cursor, downloaded=downloaded,
                        latest_post_at=latest_post_at)


def open_context(user_data_dir: Path, *, headful: bool):
    """Abre um persistent context do chromium com a sessao da burner.

    ignore_https_errors: nesta maquina o Avast intercepta o TLS e re-assina com CA
    propria; o context.request (Node, usado p/ baixar a imagem do fbcdn) nao confia
    nela e falha com 'unable to verify the first certificate'. Aceito porque o
    'MITM' e o proprio antivirus local — mesma logica do truststore no lado Python."""
    from playwright.sync_api import sync_playwright  # lazy: so quando de fato scrapeia
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        str(user_data_dir), headless=not headful, ignore_https_errors=True,
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
