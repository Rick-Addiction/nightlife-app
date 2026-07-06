# src/nightlife/ingestion/ra_source.py
"""Fonte real: eventos de nightlife de SP via a API GraphQL do Resident Advisor.

O endpoint GraphQL (ra.co/graphql) e acessivel via httpx puro (o Cloudflare so
protege as paginas HTML). O parse e PURO/testavel; a classe RASource pagina.
RA da nome+endereco do venue, mas NAO da geo (location volta 0,0) — o geo vem de
dedup c/ OSM ou do Google Places depois."""
from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from ..extraction.base import parse_iso
from .base import RawEvent, RawVenue

RA_ENDPOINT = "https://ra.co/graphql"
SP_AREA_ID = 400  # area(areaUrlName="saopaulo", countryUrlCode="br") -> id 400
_SP_TZ = ZoneInfo("America/Sao_Paulo")
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

_QUERY = """query($f: FilterInputDtoInput, $ps: Int, $page: Int) {
  eventListings(filters: $f, pageSize: $ps, page: $page) {
    data { event {
      id title date startTime contentUrl
      artists { name } genres { name }
      venue { id name address contentUrl }
    } }
    totalResults
  }
}"""


def _ra_datetime(s: str | None) -> datetime | None:
    dt = parse_iso(s)
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=_SP_TZ)  # RA da hora local de SP, sem tz


def _venue_of(v: dict) -> RawVenue | None:
    """RawVenue do venue do RA. TBA (nome=endereco, sem contentUrl) -> None (nao cria lixo)."""
    name = (v.get("name") or "").strip()
    if not name or name.upper().startswith("TBA"):
        return None
    content = v.get("contentUrl")
    return RawVenue(
        name=name,
        source_type="ra",
        lat=None, lng=None,  # RA nao expoe geo (location=0,0)
        address=(v.get("address") or "").strip() or None,
        category="nightclub",  # RA so lista nightlife
        source_url=f"https://ra.co{content}" if content else None,
    )


def parse_ra_events(data: dict, *, reference: date) -> list[RawEvent]:
    """JSON do eventListings do RA -> RawEvents. Puro. Descarta sem titulo e passados (dia SP)."""
    listings = ((data.get("data") or {}).get("eventListings")) or {}
    out: list[RawEvent] = []
    for edge in listings.get("data") or []:
        e = edge.get("event") or {}
        title = (e.get("title") or "").strip()
        if not title:
            continue
        starts = _ra_datetime(e.get("startTime") or e.get("date"))
        if starts is not None and starts.astimezone(_SP_TZ).date() < reference:
            continue
        artists = [a.get("name") for a in (e.get("artists") or []) if a.get("name")]
        genres = e.get("genres") or []
        content = e.get("contentUrl")
        url = f"https://ra.co{content}" if content else None
        out.append(RawEvent(
            name=title,
            source_type="ra",
            starts_at=starts,
            venue=_venue_of(e.get("venue") or {}),
            lineup_text=", ".join(artists) or None,
            genre=(genres[0].get("name") if genres else None),
            ticket_url=url,
            source_url=url,
            raw_payload=json.dumps(e, ensure_ascii=False, sort_keys=True),
        ))
    return out
