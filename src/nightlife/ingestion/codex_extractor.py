# src/nightlife/ingestion/codex_extractor.py
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
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
    imagem como input, resultado no stdout. Tres calibracoes necessarias:
    (1) no Windows o `codex` instalado via npm resolve para um shim
    `codex.CMD`, que subprocess.run nao consegue executar diretamente
    (WinError 2) sem `shell=True`; resolvemos o caminho completo via
    shutil.which e usamos shell so no Windows;
    (2) `-i/--image` aceita `FILE...` (multiplos valores) e por isso e
    "guloso": se o PROMPT vier depois de `-i <path>` na linha de comando,
    o parser do CLI engole o prompt como se fosse mais um arquivo de imagem;
    (3) com `shell=True` no Windows a lista de args e serializada numa unica
    string para o `cmd.exe /c`, cujo parser trunca a linha em quebras de
    linha literais — o PROMPT (multi-linha) nunca chegava inteiro ao codex.
    Por isso o PROMPT e enviado via stdin (`-` como posicional, doc do CLI:
    "instructions are read from stdin") em vez de argv, e soh o caminho da
    imagem (sem quebras de linha) trafega na linha de comando.
    """
    codex_bin = shutil.which("codex") or "codex"
    result = subprocess.run(
        [codex_bin, "exec", "--skip-git-repo-check", "-", "-i", str(image_path)],
        input=prompt,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300, shell=(sys.platform == "win32"),
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
