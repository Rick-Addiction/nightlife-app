# src/nightlife/ingestion/handle_discovery.py
"""Descoberta de @handle de IG das fontes ja capturadas (spec §5.2).

Puro na leitura de HTML (handle_from_html); a orquestracao recebe um `fetch`
injetavel (Callable[str, str|None]) — testes offline, e o runner injeta httpx.
"""
from __future__ import annotations

from ..extraction.jsonld import _iter_jsonld
from ..extraction.social import handle_from_jsonld, handles_from_text


def handle_from_html(html: str | None) -> str | None:
    """Handle de IG de uma pagina: tenta JSON-LD (sameAs), cai pra texto/links."""
    if not html:
        return None
    for node in _iter_jsonld(html):
        h = handle_from_jsonld(node)
        if h:
            return h
    found = handles_from_text(html)
    return sorted(found)[0] if found else None
