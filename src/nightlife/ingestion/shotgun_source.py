# src/nightlife/ingestion/shotgun_source.py
"""Fonte real #4: eventos de SP do Shotgun (shotgun.live), a plataforma de
ingressos mais usada pela cena de festas independentes/eletronicas de SP.

Sondado em 2026-10-28: a pagina da cidade (/pt-br/cities/sao-paulo) e
server-rendered, em ordem cronologica, paginada por `?page=N` (12 cards por
pagina; o botao "Ver mais" e um link pra essa URL). Nao ha API publica nem
__NEXT_DATA__; os cards sao <a href="/pt-br/events/<slug>"> com nome, venue
(ou so o bairro/cidade, quando o local nao e divulgado), "DD de mes. | HH:MM",
preco/status e tags de genero. Sem ano na data: inferido pela referencia.

`parse_cards` e PURO (testavel offline); `ShotgunSource.events()` pagina ate o
horizonte e devolve RawEvents (venue EMBUTIDO por nome, sem geo/endereco — o
pipeline ancora por similaridade de nome no catalogo).
"""
from __future__ import annotations

import html as htmlmod
import json
import logging
import re
import time
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .base import RawEvent, RawEventPage, RawVenue

_log = logging.getLogger(__name__)

SHOTGUN_CITY_URL = "https://shotgun.live/pt-br/cities/sao-paulo"
SHOTGUN_BASE = "https://shotgun.live"
# UA de navegador: o site devolve a listagem completa pra browsers (sondado);
# o UA do projeto nao foi testado contra o Cloudflare deles.
_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
_SP_TZ = ZoneInfo("America/Sao_Paulo")

_CARD_RE = re.compile(r'<a[^>]+href="(/pt-br/events/[^"?#]+)"[^>]*>(.*?)</a>', re.S)
_MONTHS = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
           "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
_DATE_RE = re.compile(r"\b(\d{1,2}) de (jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.?"
                      r"(?:\s*\|\s*(\d{1,2}):(\d{2}))?", re.I)
_PRICE_RE = re.compile(r"^(R\$\s?[\d.,]+|Gratuito|Esgotado|Lista de espera)$", re.I)
_PLUS_RE = re.compile(r"^\+\d+$")

# Quando o local nao e divulgado, o card traz so o bairro/cidade no lugar do
# venue. Isso NAO pode virar venue no catalogo (seria lixo "Sao Paulo").
_AREA_NAMES = {
    "sao paulo", "sp", "brasil", "centro", "centro historico", "centro historico de sao paulo",
    "pinheiros", "barra funda", "mooca", "campos eliseos", "consolacao", "bela vista",
    "bixiga", "vila madalena", "vila mariana", "santa cecilia", "itaim bibi", "jardins",
    "lapa", "perdizes", "liberdade", "bras", "republica", "se", "augusta", "paulista",
    "tatuape", "santana", "butanta", "vila olimpia", "moema", "ipiranga", "vila leopoldina",
    "jardim sapopemba", "parque regina", "parque dos camargos", "zona leste", "zona oeste",
    "zona norte", "zona sul",
}


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9, ]+", " ", s)          # tira emoji/bandeira/pontuacao
    s = re.sub(r",?\s*brasil\b", "", s)          # "Consolacao, Brasil" -> "consolacao"
    return re.sub(r"\s+", " ", s).strip(" ,")


def is_area_name(venue_text: str | None) -> bool:
    """'Sao Paulo', 'Pinheiros', 'Consolacao, Brasil' -> True (nao e venue)."""
    if not venue_text:
        return True
    return _norm(venue_text) in _AREA_NAMES


def _lines(inner_html: str) -> list[str]:
    txt = htmlmod.unescape(re.sub(r"<[^>]+>", "\n", inner_html))
    return [re.sub(r"\s+", " ", ln).strip() for ln in txt.split("\n") if ln.strip()]


def infer_year(day: int, month: int, *, reference: date) -> int:
    """Listagem so tem futuros: mes anterior ao de referencia => ano que vem."""
    year = reference.year
    if month < reference.month or (month == reference.month and day < reference.day - 1):
        year += 1
    return year


def _starts_at(text: str, *, reference: date) -> datetime | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    day, mon = int(m.group(1)), _MONTHS[m.group(2).lower()]
    hour = int(m.group(3)) if m.group(3) else 0
    minute = int(m.group(4)) if m.group(4) else 0
    try:
        return datetime(infer_year(day, mon, reference=reference), mon, day, hour, minute, tzinfo=_SP_TZ)
    except ValueError:
        return None


def parse_cards(html: str, *, reference: date) -> list[RawEvent]:
    """HTML da listagem -> RawEvents. Puro. Descarta cards sem nome/sem data e
    passados (dia SP). Venue = 2a linha do card, a menos que seja so um bairro."""
    out: list[RawEvent] = []
    seen: set[str] = set()
    for m in _CARD_RE.finditer(html):
        href, lines = m.group(1), _lines(m.group(2))
        if not lines or href in seen:
            continue
        seen.add(href)
        name = lines[0]
        starts = _starts_at(" ".join(lines[1:]), reference=reference)
        if starts is None or starts.astimezone(_SP_TZ).date() < reference:
            continue
        venue_text = lines[1] if len(lines) > 1 and not _DATE_RE.search(lines[1]) else None
        price = status = None
        tags: list[str] = []
        after_price = False
        for ln in lines[2:]:
            if _PRICE_RE.match(ln):
                after_price = True
                (price, status) = (ln, None) if ln.upper().startswith("R$") or ln.lower() == "gratuito" else (None, ln)
                continue
            if after_price and not _PLUS_RE.match(ln) and not _DATE_RE.search(ln) and ln != "|":
                tags.append(ln)
        url = f"{SHOTGUN_BASE}{href}"
        venue = None
        if venue_text and not is_area_name(venue_text):
            venue = RawVenue(name=venue_text, source_type="shotgun", category="nightclub",
                             source_url=None)
        out.append(RawEvent(
            name=name,
            source_type="shotgun",
            starts_at=starts,
            venue=venue,
            genre=(tags[0] if tags else None),
            ticket_url=url,
            source_url=url,
            raw_payload=json.dumps({"url": url, "lines": lines, "venue_text": venue_text,
                                    "price": price, "status": status, "tags": tags},
                                   ensure_ascii=False, sort_keys=True),
        ))
    return out


class ShotgunSource:
    """Fonte real #4: listagem cronologica de SP do Shotgun, paginada."""

    def __init__(self, *, city_url: str = SHOTGUN_CITY_URL, max_pages: int = 40,
                 horizon_days: int = 45, reference: date | None = None,
                 timeout: float = 40.0, pause_s: float = 0.6) -> None:
        self._city_url = city_url
        self._max_pages = max_pages
        self._horizon_days = horizon_days
        self._reference = reference
        self._timeout = timeout
        self._pause_s = pause_s

    def venues(self) -> list[RawVenue]:
        return []  # venues vem EMBUTIDOS nos eventos

    def event_pages(self) -> list[RawEventPage]:
        return []

    def page_url(self, page: int) -> str:
        return self._city_url if page == 0 else f"{self._city_url}?page={page}"

    def events(self) -> list[RawEvent]:
        reference = self._reference or datetime.now(_SP_TZ).date()
        horizon = reference + timedelta(days=self._horizon_days)
        out: list[RawEvent] = []
        seen: set[str] = set()
        for page in range(0, self._max_pages):
            resp = httpx.get(self.page_url(page),
                             headers={"User-Agent": _USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"},
                             timeout=self._timeout, follow_redirects=True)
            resp.raise_for_status()
            batch = [e for e in parse_cards(resp.text, reference=reference) if e.source_url not in seen]
            if not batch:
                break
            seen.update(e.source_url for e in batch if e.source_url)
            out.extend(batch)
            # listagem cronologica: a pagina inteira alem do horizonte => acabou
            if all(e.starts_at is not None and e.starts_at.astimezone(_SP_TZ).date() > horizon
                   for e in batch):
                break
            time.sleep(self._pause_s)
        else:
            _log.warning("ShotgunSource: cap de %d paginas atingido — resultados possivelmente truncados",
                         self._max_pages)
        return out
