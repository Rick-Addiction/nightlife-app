# src/nightlife/ingestion/feed_source.py
"""Feed 'Seguindo' como fonte de deteccao (Ciclo E-3). Reusa os helpers de no
do instagram_source (shape moderno+legado); a diferenca do timeline de PERFIL e
que cada no do FEED carrega o @autor. parse_feed_items e PURO (fixture do probe)."""
from __future__ import annotations

from dataclasses import dataclass

from .instagram_source import _shortcode_of, _taken_at_of

# connection do feed CONFIRMADA no probe real (2026-07-13)
_FEED_KEY = "xdt_api__v1__feed__timeline__connection"


@dataclass
class FeedItem:
    handle: str
    shortcode: str
    taken_at: int | None


def _feed_edges(graphql: dict) -> list:
    conn = (graphql.get("data") or {}).get(_FEED_KEY)
    return conn.get("edges") or [] if isinstance(conn, dict) else []


def parse_feed_items(graphql: dict) -> list[FeedItem]:
    """O post fica em edge.node.media (ads/sugestoes tem media=None). @autor em
    media.user.username; shortcode/taken_at pelos helpers de no do instagram_source."""
    out: list[FeedItem] = []
    for edge in _feed_edges(graphql):
        media = (edge.get("node") or {}).get("media")
        if not isinstance(media, dict) or not media:   # ad/sugestao/story
            continue
        handle = (media.get("user") or {}).get("username")
        shortcode = _shortcode_of(media)
        if not handle or not shortcode:
            continue
        out.append(FeedItem(handle=handle, shortcode=shortcode,
                            taken_at=_taken_at_of(media)))
    return out


def new_since_cursor(items: list[FeedItem],
                     cursor_by_handle: dict[str, str]) -> list[FeedItem]:
    """Itens mais novos que o ultimo shortcode visto de cada handle. O feed vem
    do mais novo pro mais antigo, entao pra cada handle paramos ao bater no
    cursor. Handle sem cursor (nunca visto) -> todos os seus itens sao novos."""
    seen_cursor: set[str] = set()
    out: list[FeedItem] = []
    for it in items:
        cur = cursor_by_handle.get(it.handle)
        if cur is not None and (it.shortcode == cur or it.handle in seen_cursor):
            seen_cursor.add(it.handle)     # deste handle pra baixo e tudo antigo
            continue
        out.append(it)
    return out


def playwright_fetch_feed(context) -> list[FeedItem]:
    """Abre o feed 'Seguindo' e captura o JSON; parse_feed_items (puro) extrai.
    BRITTLE (o IG muda): a URL/rolagem sao calibradas no probe/smoke."""
    page = context.new_page()
    captured: list[dict] = []

    def _on_response(resp):
        if "application/json" not in resp.headers.get("content-type", ""):
            return
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return
        if isinstance(data, dict):
            captured.append(data)

    page.on("response", _on_response)
    page.goto("https://www.instagram.com/?variant=following",
              wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(3000)
    page.mouse.wheel(0, 3000)
    page.wait_for_timeout(2500)
    page.close()
    items: list[FeedItem] = []
    for data in captured:
        got = parse_feed_items(data)
        if got:
            items = got
            break
    return items
