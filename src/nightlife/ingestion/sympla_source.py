# src/nightlife/ingestion/sympla_source.py
from __future__ import annotations

import json
from datetime import date
from zoneinfo import ZoneInfo

import httpx

from ..extraction.base import parse_iso
from .base import RawEvent, RawEventPage, RawVenue

SYMPLA_SEARCH_ENDPOINT = "https://www.sympla.com.br/api/v1/search"
_USER_AGENT = "nightlife-app/0.1 (uso pessoal; contato: henrique.rachti@gmail.com)"
_SP_TZ = ZoneInfo("America/Sao_Paulo")

# Escopo (spec sympla §2, opcao b do usuario): tema "Festas e Shows" inteiro.
# Valores observados na API real em 2026-07-03; a colecao e o cinto-e-suspensorio.
_CITY = "São Paulo"
_PARTY_THEME = "Festas e Shows"
_PARTY_COLLECTION = "FESTA E SHOW"


def _wanted(record: dict) -> bool:
    if (record.get("city") or "").strip() != _CITY:
        return False
    theme = (record.get("theme_name") or "").strip()
    collections = record.get("collection_name") or []
    return theme == _PARTY_THEME or _PARTY_COLLECTION in collections


def parse_search_records(data: dict, *, reference: date) -> list[RawEvent]:
    """Registros da API de busca da Sympla -> RawEvents. Puro: testavel offline.

    Filtro client-side GARANTIDO (o server-side e best-effort): cidade =
    Sao Paulo, tema festas/shows, e so eventos de hoje (dia SP) em diante.
    Descarta registros sem name.
    """
    out: list[RawEvent] = []
    for rec in data.get("data") or []:
        name = rec.get("name")
        if not name or not _wanted(rec):
            continue
        starts = parse_iso(rec.get("start_date_utc") or rec.get("start_date"))
        if starts is not None and starts.astimezone(_SP_TZ).date() < reference:
            continue  # so futuros (dia SP)
        ends = parse_iso(rec.get("end_date_utc") or rec.get("end_date"))
        loc = rec.get("location") or {}
        venue = None
        if loc.get("name"):
            venue = RawVenue(
                name=loc["name"],
                source_type="ticketing",
                lat=loc.get("lat"),
                lng=loc.get("lon"),
                address=(loc.get("address") or "").strip() or None,
                category=None,
                source_url=rec.get("url"),
            )
        organizer = rec.get("organizer") or {}
        out.append(RawEvent(
            name=name,
            source_type="ticketing",
            starts_at=starts,
            ends_at=ends,
            venue=venue,
            organizer_name=(organizer.get("name") or "").strip() or None,
            genre=(rec.get("format_name") or rec.get("theme_name") or "").strip() or None,
            ticket_url=rec.get("url"),
            source_url=rec.get("url"),
            # sort_keys: hash estavel entre execucoes (idempotencia da evidencia)
            raw_payload=json.dumps(rec, ensure_ascii=False, sort_keys=True),
        ))
    return out


class SymplaSource:
    """Fonte real #2: eventos de festas/shows de SP via API de busca da Sympla."""

    def __init__(self, *, endpoint: str = SYMPLA_SEARCH_ENDPOINT,
                 page_size: int = 100, max_pages: int = 20,
                 reference: date | None = None, timeout: float = 30.0) -> None:
        self._endpoint = endpoint
        self._page_size = page_size
        self._max_pages = max_pages
        self._reference = reference
        self._timeout = timeout

    def venues(self) -> list[RawVenue]:
        return []  # venues vem EMBUTIDOS nos eventos

    def event_pages(self) -> list[RawEventPage]:
        return []

    def events(self) -> list[RawEvent]:
        reference = self._reference or date.today()
        out: list[RawEvent] = []
        for page in range(1, self._max_pages + 1):
            resp = httpx.post(
                self._endpoint,
                json={"service": "/v4/search",
                      "params": {"cityIn": [_CITY], "limit": self._page_size, "page": page}},
                headers={"User-Agent": _USER_AGENT, "Content-Type": "application/json"},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("data") or []
            out.extend(parse_search_records(data, reference=reference))
            if len(batch) < self._page_size:
                break
        return out
