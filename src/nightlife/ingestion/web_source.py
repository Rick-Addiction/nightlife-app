# src/nightlife/ingestion/web_source.py
"""Fetch de site de venue + descoberta da pagina de agenda (Ciclo E-2a).
Parsers PUROS (agenda_links/looks_empty/visible_text) testados; fetch_page e
shell smoke-calibrado (httpx -> Playwright de fallback)."""
from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

_AGENDA_WORDS = ("agenda", "eventos", "evento", "programacao", "programa", "shows", "line")
_JSONLD_RE = re.compile(r'type=["\']application/ld\+json["\']', re.I)
_TEXT_MIN = 200          # abaixo disso + sem jsonld => provavelmente JS-render vazio


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) != "Mn")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def visible_text(html: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 — html quebrado: devolve o que juntou
        pass
    return " ".join(p.parts)


def looks_empty(html: str) -> bool:
    if _JSONLD_RE.search(html):
        return False
    return len(visible_text(html)) < _TEXT_MIN


class _LinkGrabber(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []   # (href, texto)
        self._href = None
        self._buf: list[str] = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._buf = []
    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._buf)))
            self._href = None


def agenda_links(html: str, *, base_url: str, cap: int = 3) -> list[str]:
    g = _LinkGrabber()
    try:
        g.feed(html)
    except Exception:  # noqa: BLE001
        pass
    host = urlparse(base_url).netloc
    out: list[str] = []
    for href, txt in g.links:
        blob = _norm(f"{href} {txt}")
        if not any(w in blob for w in _AGENDA_WORDS):
            continue
        absu = urljoin(base_url, href)
        if urlparse(absu).netloc != host:      # so mesmo dominio
            continue
        if absu not in out:
            out.append(absu)
        if len(out) >= cap:
            break
    return out


def fetch_page(url: str, *, timeout: float = 15.0) -> str:
    """httpx primeiro; se looks_empty, Playwright renderiza. Shell smoke."""
    import httpx
    import truststore
    truststore.inject_into_ssl()
    headers = {"User-Agent": "RadarSP/1.0 (agenda de eventos; contato via github)"}
    html = ""
    try:
        r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        html = r.text
    except Exception:  # noqa: BLE001 — rede/tls: tenta o Playwright
        html = ""
    if html and not looks_empty(html):
        return html
    # fallback renderizado
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            page = b.new_page(user_agent=headers["User-Agent"])
            try:
                page.goto(url, wait_until="networkidle", timeout=int(timeout * 1000))
                page.wait_for_timeout(1500)
                html = page.content()
            finally:
                page.close(); b.close()
    except Exception:  # noqa: BLE001 — sem render: devolve o httpx (mesmo que vazio)
        pass
    return html
