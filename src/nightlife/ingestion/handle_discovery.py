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

from ..domain.nightlife_relevance import is_buffet_name, is_platform_handle
from ..extraction.jsonld import _iter_jsonld
from ..extraction.social import (
    _IG_URL, _handle_if_ig_url, handle_from_jsonld, handle_from_osm_tags,
    ig_handles_from_urls,
)
from ..models import Event, EventSource, Organizer, Venue, VenueSource

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
    found = ig_handles_from_urls(html)  # so URLs de IG; @mencoes em HTML sao ruido (CSS/JSON-LD)
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
        if is_buffet_name(v.name):
            continue                                  # buffet: nem descobre nem fetch
        url = _osm_source_url(session, v.id)
        tags = osm_tags_by_url.get(url, {}) if url else {}
        handle = handle_from_osm_tags(tags)
        website = tags.get("website") or tags.get("contact:website")
        if website and not v.website:
            v.website = website
        # site oficial ja no banco (ex.: websiteUri do Places, Ciclo A) tambem
        # e fonte; a tag OSM tem precedencia quando existe
        fetch_url = website or v.website
        if handle is None and fetch_url:
            if _IG_URL.search(fetch_url):
                # o "site" e uma URL do proprio instagram: ou e perfil (handle
                # direto, GUARDADO — canonical_handle cru aceitaria dominio
                # pelado tipo 'selva.club' como handle), ou nao-perfil
                # (/invites/...) — e fetch de instagram.com nunca vale a pena
                handle = _handle_if_ig_url(fetch_url)
            else:
                try:
                    handle = handle_from_html(fetch(fetch_url))
                except Exception as exc:  # noqa: BLE001 — fetch best-effort, nao fatal
                    _log.warning("fetch de %s falhou: %s", fetch_url, exc)
        if handle and not is_platform_handle(handle):
            v.instagram = handle
            count += 1
    return count


def discover_organizer_handles(session: Session, *, fetch: Fetcher) -> int:
    """Popula organizer.instagram via a pagina de detalhe da Sympla (source_url
    de um EventSource do organizer). Idempotente. Retorna quantos novos."""
    count = 0
    orgs = session.scalars(select(Organizer).where(Organizer.instagram.is_(None))).all()
    for org in orgs:
        src = session.scalars(
            select(EventSource)
            .join(Event, EventSource.event_id == Event.id)
            .where(Event.organizer_id == org.id, EventSource.source_url.is_not(None))
        ).first()
        if src is None or not src.source_url:
            continue
        try:
            handle = handle_from_html(fetch(src.source_url))
        except Exception as exc:  # noqa: BLE001 — best-effort
            _log.warning("fetch de %s falhou: %s", src.source_url, exc)
            continue
        if handle and not is_platform_handle(handle):
            org.instagram = handle
            count += 1
    return count
