# src/nightlife/extraction/freetext.py
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse

from ..domain.dates_ptbr import parse_ptbr_datetime
from .base import ExtractedEvent

# hosts de link "generico" (perfil/bio do venue, grupo de zap): NAO sao ticket.
# Guardar isso em ticket_url quebraria o dedupe, que trata ticket igual como
# prova de mesmo-evento.
_GENERIC_LINK_HOSTS = {
    "linktr.ee", "linktree.com", "wa.me", "api.whatsapp.com", "chat.whatsapp.com",
    "instagram.com", "facebook.com", "m.facebook.com", "youtube.com", "youtu.be",
    "open.spotify.com", "t.me",
}


def _clean_url(url: str) -> str:
    """Remove pontuacao de prosa do fim da URL sem corromper URLs legitimas.

    Fechos (parenteses etc.) so caem quando desbalanceados — "...(https://x)."
    perde o ")", mas "https://x/evento_(2)" fica intacto.
    """
    url = url.rstrip(".,;:!?\"'")
    for open_c, close_c in (("(", ")"), ("[", "]"), ("{", "}")):
        while url.endswith(close_c) and url.count(close_c) > url.count(open_c):
            url = url[:-1].rstrip(".,;:!?\"'")
    return url


def _is_generic_link(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host in _GENERIC_LINK_HOSTS


def extract_freetext_deterministic(
    text: str, *, reference: date, source_url: str | None = None
) -> ExtractedEvent:
    ev = ExtractedEvent(source_url=source_url, raw={"text": text})

    pd = parse_ptbr_datetime(text, reference=reference)
    ev.starts_at = pd.dt
    ev.starts_at_raw = pd.matched
    if pd.dt is not None:
        ev.field_confidence["starts_at"] = 0.5 if pd.ambiguous else 0.9

    for line in text.splitlines():
        if line.strip():
            ev.name = line.strip()
            break

    m = re.search(r"https?://\S+", text)
    if m:
        url = _clean_url(m.group(0))
        if not _is_generic_link(url):
            ev.ticket_url = url

    return ev
