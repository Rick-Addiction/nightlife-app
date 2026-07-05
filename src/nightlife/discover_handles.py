# src/nightlife/discover_handles.py
"""Descobre @handles de IG dos venues/organizers ja no banco.

Uso: .venv/Scripts/python -m nightlife.discover_handles
"""
from __future__ import annotations

import truststore

truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

import httpx

from .db import SessionLocal
from .ingestion.handle_discovery import discover_organizer_handles, discover_venue_handles
from .ingestion.osm_source import OVERPASS_ENDPOINT, SP_BBOX, _build_query, parse_overpass_tags

_USER_AGENT = "nightlife-app/0.1 (uso pessoal; contato: henrique.rachti@gmail.com)"


def _fetch(url: str) -> str | None:
    try:
        resp = httpx.get(url, headers={"User-Agent": _USER_AGENT},
                         timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception:  # noqa: BLE001 — best-effort; o orquestrador loga
        return None


def _osm_tags_by_url() -> dict:
    """1 chamada ao Overpass -> {source_url do OSM: tags} (as tags nao ficam no DB)."""
    try:
        resp = httpx.post(OVERPASS_ENDPOINT, data={"data": _build_query(SP_BBOX)},
                          headers={"User-Agent": _USER_AGENT}, timeout=90.0)
        resp.raise_for_status()
        return parse_overpass_tags(resp.json())
    except Exception:  # noqa: BLE001 — sem tags OSM, cai so pra veia Sympla
        return {}


def main() -> None:
    with SessionLocal() as session:
        osm_tags = _osm_tags_by_url()
        nv = discover_venue_handles(session, osm_tags_by_url=osm_tags, fetch=_fetch)
        no = discover_organizer_handles(session, fetch=_fetch)
        session.commit()
        print(f"handles novos — venues: {nv} | organizers: {no}")


if __name__ == "__main__":
    main()
