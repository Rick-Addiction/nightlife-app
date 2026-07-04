# src/nightlife/ingestion/flyer_source.py
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from ..extraction.flyer import FlyerExtractor, flyer_to_raw_event
from ..extraction.imagehash import dhash
from .base import RawEvent, RawEventPage, RawVenue

_log = logging.getLogger(__name__)

_IMAGE_GLOBS = ("*.jpg", "*.jpeg", "*.png", "*.webp")


class FlyerSource:
    """Fonte de flyers: varre um inbox de imagens, extrai via FlyerExtractor.

    Expoe processed_paths (extraidos com sucesso + duplicatas por dHash) e
    failed_paths (extracao falhou ou sem nome de evento) para o runner mover —
    protecao de cota: imagem processada nunca e re-extraida.
    """

    def __init__(self, directory: Path | str, extractor: FlyerExtractor,
                 *, reference: date) -> None:
        self._dir = Path(directory)
        self._extractor = extractor
        self._reference = reference
        self.processed_paths: list[Path] = []
        self.failed_paths: list[Path] = []

    def venues(self) -> list[RawVenue]:
        return []

    def event_pages(self) -> list[RawEventPage]:
        return []

    def events(self) -> list[RawEvent]:
        self.processed_paths = []
        self.failed_paths = []
        out: list[RawEvent] = []
        seen_hashes: set[str] = set()

        images = sorted(p for g in _IMAGE_GLOBS for p in self._dir.glob(g))
        for path in images:
            image_hash = dhash(path)
            if image_hash in seen_hashes:
                self.processed_paths.append(path)  # duplicata: nao gasta extracao
                continue
            seen_hashes.add(image_hash)

            extraction = self._extractor.extract(path)
            raw_event = (flyer_to_raw_event(extraction, image_hash, reference=self._reference)
                         if extraction is not None else None)
            if raw_event is None:
                _log.warning("flyer %s: extracao falhou ou sem nome de evento", path.name)
                self.failed_paths.append(path)
                continue
            out.append(raw_event)
            self.processed_paths.append(path)
        return out
