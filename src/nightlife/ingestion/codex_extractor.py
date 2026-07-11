# src/nightlife/ingestion/codex_extractor.py
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from ..extraction.flyer import FlyerExtraction
from .codex_cli import extract_json, run_codex

_log = logging.getLogger(__name__)

# aliases internos preservados: alguns testes acessam os nomes privados
# (ex.: `ce._run_codex(...)`, `ce.subprocess.run` monkeypatch)
_run_codex = run_codex
_extract_json = extract_json

_PROMPT = """Voce esta lendo a IMAGEM de um flyer de festa/evento de Sao Paulo.
Extraia APENAS o que esta escrito no flyer e responda com UM UNICO objeto JSON,
sem markdown e sem texto antes ou depois, exatamente neste formato:

{"event_name": str|null, "date_text": str|null, "venue_name": str|null,
 "organizer": str|null, "lineup": [str], "price_text": str|null,
 "ticket_url": str|null, "instagram_handle": str|null,
 "quotes": {campo: trecho do flyer que sustenta o valor},
 "confidence": {campo: 0.0 a 1.0}}

Regras:
- Campo ausente no flyer = null. NUNCA invente valores.
- date_text: copie o texto da data EXATAMENTE como esta no flyer
  (ex: "SEX 13/06 23h"). Nao converta, nao interprete, nao calcule.
- quotes: para cada campo preenchido, o trecho do flyer que o sustenta.
- lineup: nomes dos artistas como escritos, na ordem do flyer."""


class CodexExtractor:
    """FlyerExtractor via codex exec (assinatura). Runner injetavel p/ testes."""

    def __init__(self, *, runner: Callable[[Path, str], str] | None = None,
                 retries: int = 1) -> None:
        self._runner = runner or run_codex
        self._retries = retries

    def extract(self, image_path: Path, *, caption: str | None = None) -> FlyerExtraction | None:
        base = _PROMPT
        if caption:
            base = (_PROMPT + "\n\nDICA — a legenda do post que acompanha o flyer diz "
                    f"(use como apoio, mas a IMAGEM manda; nao invente):\n{caption}")
        prompt = base
        for attempt in range(self._retries + 1):
            try:
                output = self._runner(image_path, prompt)
                data = extract_json(output)
                return FlyerExtraction.model_validate(data)
            except (ValueError, json.JSONDecodeError, ValidationError,
                    subprocess.SubprocessError, OSError) as exc:
                _log.warning("extracao de %s falhou (tentativa %d): %s",
                             image_path, attempt + 1, exc)
                prompt = (base + "\n\nATENCAO: sua resposta anterior foi invalida "
                          f"({exc}). Responda APENAS com o objeto JSON.")
        return None
