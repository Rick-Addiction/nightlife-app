# src/nightlife/ingestion/codex_extractor.py
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from ..extraction.flyer import FlyerExtraction

_log = logging.getLogger(__name__)

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


def _run_codex(image_path: Path, prompt: str) -> str:
    """Invoca o codex CLI em modo nao-interativo com a imagem anexada.

    Flags calibrados no smoke real (Task 5) — requisito: exec headless,
    imagem como input, resultado no stdout.
    """
    result = subprocess.run(
        ["codex", "exec", "--skip-git-repo-check", "-i", str(image_path), prompt],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300,
    )
    return result.stdout or ""


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("nenhum objeto JSON na saida")
    return json.loads(text[start:end + 1])


class CodexExtractor:
    """FlyerExtractor via codex exec (assinatura). Runner injetavel p/ testes."""

    def __init__(self, *, runner: Callable[[Path, str], str] | None = None,
                 retries: int = 1) -> None:
        self._runner = runner or _run_codex
        self._retries = retries

    def extract(self, image_path: Path) -> FlyerExtraction | None:
        prompt = _PROMPT
        for attempt in range(self._retries + 1):
            try:
                output = self._runner(image_path, prompt)
                data = _extract_json(output)
                return FlyerExtraction.model_validate(data)
            except (ValueError, json.JSONDecodeError, ValidationError,
                    subprocess.SubprocessError, OSError) as exc:
                _log.warning("extracao de %s falhou (tentativa %d): %s",
                             image_path, attempt + 1, exc)
                prompt = (_PROMPT + "\n\nATENCAO: sua resposta anterior foi invalida "
                          f"({exc}). Responda APENAS com o objeto JSON.")
        return None
