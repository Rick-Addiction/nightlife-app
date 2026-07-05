# src/nightlife/ingestion/handle_discovery.py
"""Descoberta de @handle de IG das fontes ja capturadas (spec §5.2).

Puro na leitura de HTML (handle_from_html); a orquestracao recebe um `fetch`
injetavel (Callable[str, str|None]) — testes offline, e o runner injeta httpx.
"""
from __future__ import annotations

import logging
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..extraction.jsonld import _iter_jsonld
from ..extraction.social import (
    canonical_handle, handle_from_jsonld, handle_from_osm_tags, handles_from_text,
)
from ..models import Venue, VenueSource

_log = logging.getLogger(__name__)

Fetcher = Callable[[str], "str | None"]


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


def _osm_source_url(session: Session, venue_id: int) -> str | None:
    src = session.scalars(
        select(VenueSource).where(
            VenueSource.venue_id == venue_id, VenueSource.source_type == "osm"
        )
    ).first()
    return src.source_url if src is not None else None


def discover_venue_handles(
    session: Session, *, osm_tags_by_url: dict[str, dict], fetch: Fetcher
) -> int:
    """Popula venue.instagram/website p/ venues sem instagram. Retorna quantos novos.

    `osm_tags_by_url`: {source_url do OSM -> tags} (o runner monta via 1 chamada ao
    Overpass). 1) tag OSM (contact:instagram/website); 2) se ha website nao-IG,
    fetch da pagina -> handle_from_html. Idempotente: pula quem ja tem instagram."""
    count = 0
    venues = session.scalars(select(Venue).where(Venue.instagram.is_(None))).all()
    for v in venues:
        url = _osm_source_url(session, v.id)
        tags = osm_tags_by_url.get(url, {}) if url else {}
        handle = handle_from_osm_tags(tags)
        website = tags.get("website") or tags.get("contact:website")
        if website and not v.website:
            v.website = website
        if handle is None and website and canonical_handle(website) is None:
            try:
                handle = handle_from_html(fetch(website))
            except Exception as exc:  # noqa: BLE001 — fetch best-effort, nao fatal
                _log.warning("fetch de %s falhou: %s", website, exc)
        if handle:
            v.instagram = handle
            count += 1
    return count
