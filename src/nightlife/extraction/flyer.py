# src/nightlife/extraction/flyer.py
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from ..domain.dates_ptbr import parse_ptbr_datetime
from ..ingestion.base import RawEvent
from .freetext import _clean_url, _is_generic_link


class FlyerExtraction(BaseModel):
    """Contrato anti-alucinacao (spec §4): null p/ ausente, quotes como evidencia."""

    event_name: str | None = None
    date_text: str | None = None       # texto CRU do flyer; quem converte e o dates_ptbr
    venue_name: str | None = None
    organizer: str | None = None
    lineup: list[str] = Field(default_factory=list)
    price_text: str | None = None
    ticket_url: str | None = None
    instagram_handle: str | None = None
    quotes: dict[str, str] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)

    def adjusted_confidence(self) -> dict[str, float]:
        """Campo preenchido sem quote que o sustente e suspeito: confianca cai pela metade."""
        return {
            field: (c if field in self.quotes else c / 2)
            for field, c in self.confidence.items()
        }


class FlyerExtractor(Protocol):
    def extract(self, image_path: Path, *, caption: str | None = None) -> FlyerExtraction | None: ...


def flyer_to_raw_event(
    extraction: FlyerExtraction, image_hash: str, *, reference: date,
    permalink: str | None = None, handle: str | None = None,
) -> RawEvent | None:
    """Extracao validada -> RawEvent. Pura. Descarta se nao ha nome de evento."""
    if not extraction.event_name:
        return None

    starts = None
    if extraction.date_text:
        starts = parse_ptbr_datetime(extraction.date_text, reference=reference).dt

    ticket = None
    if extraction.ticket_url:
        url = _clean_url(extraction.ticket_url.strip())
        if url and not _is_generic_link(url):
            ticket = url

    # Anti-alucinacao (spec §4): venue_name e organizer tem efeito downstream
    # (ancoram / criam Organizer). Descarta os que estao SUSPEITOS — confianca
    # ajustada < 0.5 (sem quote que os sustente, ou confianca genuinamente
    # baixa) — em vez de ancorar/criar a partir de um chute do modelo.
    adj = extraction.adjusted_confidence()
    venue_name = extraction.venue_name if adj.get("venue_name", 0.0) >= 0.5 else None
    organizer = extraction.organizer if adj.get("organizer", 0.0) >= 0.5 else None

    return RawEvent(
        name=extraction.event_name,
        source_type="vision_flyer",
        starts_at=starts,
        venue_name=venue_name,              # ancora no catalogo; nunca cria venue
        source_handle=handle,
        organizer_name=organizer,
        lineup_text=", ".join(extraction.lineup) or None,
        ticket_url=ticket,
        source_url=permalink or f"flyer:{image_hash}",
        raw_payload=extraction.model_dump_json(),
    )
