# src/nightlife/extraction/social.py
"""Extracao PURA de @handles de Instagram de URLs, texto, tags OSM e JSON-LD.

Sem rede, sem DB — e onde mora a testabilidade da descoberta (spec §5.1).
"""
from __future__ import annotations

import re

_IG_URL = re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/([^/?#\s\"'<>),\]]+)", re.IGNORECASE)
# lookbehind (?<![\w.]): nao casa @ dentro de e-mail (ex.: booking@gmail.com)
_MENTION = re.compile(r"(?<![\w.])@([A-Za-z0-9._]+)")
# caminhos do instagram.com que NAO sao perfil de usuario:
_NON_PROFILE = {
    "p", "reel", "reels", "explore", "stories", "tv", "accounts",
    "about", "directory", "developer", "legal", "privacy",
}
_VALID = re.compile(r"[a-z0-9._]{1,30}")


def canonical_handle(raw: str | None) -> str | None:
    """'@Foo', 'instagram.com/foo/', 'https://instagram.com/foo?igshid=..' -> 'foo'.

    Rejeita caminhos nao-perfil (/p/, /reel/, /explore) e valores que nao sao
    handle valido (ex.: um site proprio que nao e do instagram)."""
    if not raw:
        return None
    s = raw.strip()
    m = _IG_URL.search(s)
    if m:
        s = m.group(1)
    s = s.lstrip("@").strip().strip("/").lower()
    s = s.split("?")[0].split("/")[0].strip(".")  # tira ponto de borda (ex.: "@vhoor." no fim da frase)
    if not s or s in _NON_PROFILE:
        return None
    if not _VALID.fullmatch(s):
        return None
    return s


def handles_from_text(text: str | None) -> set[str]:
    """Todos os handles achaveis num blob de texto/HTML: URLs de IG + @mencoes."""
    if not text:
        return set()
    out: set[str] = set()
    for m in _IG_URL.finditer(text):
        h = canonical_handle(m.group(1))
        if h:
            out.add(h)
    for m in _MENTION.finditer(text):
        h = canonical_handle(m.group(1))
        if h:
            out.add(h)
    return out


def ig_handles_from_urls(text: str | None) -> set[str]:
    """So handles vindos de URLs de instagram.com — IGNORA @mencoes. Em HTML, `@`
    quase sempre e CSS at-rule (@media/@font-face) ou JSON-LD (@context), nao um
    handle; um site que linka seu IG usa a URL. Usado pelo fallback de pagina."""
    if not text:
        return set()
    out: set[str] = set()
    for m in _IG_URL.finditer(text):
        h = canonical_handle(m.group(1))
        if h:
            out.add(h)
    return out


def _handle_if_ig_url(value: str | None) -> str | None:
    """Handle so se `value` for uma URL de instagram.com — nao um dominio proprio.

    Sem isto, um `website=cargo.com.br` (dominio pelado, sem esquema) seria aceito
    como se fosse o handle 'cargo.com.br'."""
    if value and _IG_URL.search(value):
        return canonical_handle(value)
    return None


def handle_from_osm_tags(tags: dict) -> str | None:
    """Tags OSM -> handle. Chaves de instagram aceitam handle direto; chaves de
    website so contam se o valor for uma URL de instagram (nao o site proprio)."""
    for key in ("contact:instagram", "instagram"):
        h = canonical_handle(tags.get(key))
        if h:
            return h
    for key in ("contact:website", "website"):
        h = _handle_if_ig_url(tags.get(key))
        if h:
            return h
    return None


def handle_from_jsonld(data) -> str | None:
    """Varre recursivamente um no JSON-LD (dict/list/@graph) por sameAs de IG."""
    if isinstance(data, dict):
        same = data.get("sameAs")
        if isinstance(same, str):
            h = canonical_handle(same)
            if h:
                return h
        elif isinstance(same, list):
            for u in same:
                if isinstance(u, str):
                    h = canonical_handle(u)
                    if h:
                        return h
        for v in data.values():
            h = handle_from_jsonld(v)
            if h:
                return h
    elif isinstance(data, list):
        for v in data:
            h = handle_from_jsonld(v)
            if h:
                return h
    return None
