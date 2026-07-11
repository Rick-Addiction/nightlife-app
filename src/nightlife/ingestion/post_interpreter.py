# src/nightlife/ingestion/post_interpreter.py
"""Interprete de posts (spec E-1 §3.2): imagem + legenda INTEIRA + contexto do
venue -> PostInterpretation (acoes). Runner injetavel: testes offline nao
gastam cota. web_page pluga no E-2 pelo mesmo contrato."""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from pydantic import ValidationError

from ..extraction.post_actions import PostInterpretation
from .codex_cli import extract_json, run_codex

_log = logging.getLogger(__name__)


@dataclass
class Document:
    kind: Literal["ig_post"]           # "web_page" entra no E-2
    image_path: Path
    caption: str | None
    handle: str | None
    permalink: str | None


@dataclass
class VenueContext:
    venue_name: str | None
    handle: str | None
    today_iso: str
    known_events: list[tuple[str, str | None]] = field(default_factory=list)  # (nome, data ISO|None)


_PROMPT_BASE = """Voce e o editor de uma agenda de vida noturna de Sao Paulo.
Vai receber a IMAGEM de um post de Instagram e a LEGENDA completa. Entenda o
post e decida ACOES sobre a agenda. Responda com UM UNICO objeto JSON, sem
markdown, exatamente neste formato:

{"actions": [
  {"type": "add_event", "name": str, "date_text": str|null, "time_text": str|null,
   "lineup": [str], "genre": str|null, "ticket_url": str|null,
   "quotes": {campo: trecho da imagem/legenda que sustenta},
   "confidence": {campo: 0.0 a 1.0}},
  {"type": "cancel_event", "event_name": str, "event_date_text": str|null,
   "quote": str, "confidence": 0.0 a 1.0},
  {"type": "update_event", "event_name": str, "event_date_text": str|null,
   "changes": {"date_text"?: str, "name"?: str, "ticket_url"?: str},
   "quote": str, "confidence": 0.0 a 1.0},
  {"type": "ignore", "reason": "aula|aniversario|institucional|esporte|repost|sem_evento|outro",
   "note": str|null}
]}

Regras:
- Post com UMA festa -> um add_event. Post-AGENDA (programacao da semana/mes)
  -> um add_event POR festa listada, cada um com sua data.
- date_text: copie o texto da data EXATAMENTE como esta (ex: "SEX 18/07 23h").
  Nao converta, nao calcule. Sem data legivel -> null.
- Post que NAO anuncia festa (aula, curso, aniversario de cliente, transmissao
  de jogo, institucional, sorteio, cardapio) -> ignore com o reason certo.
- Se o post anuncia festa que JA ESTA na lista de eventos conhecidos abaixo
  (mesmo nome, mesma data) -> ignore com reason "repost".
- Se anuncia CANCELAMENTO ou ADIAMENTO de evento conhecido -> cancel_event ou
  update_event com quote da prova ("CANCELADA", "adiada para...").
- quotes/quote: SEMPRE o trecho literal que sustenta. NUNCA invente."""


def build_prompt(doc: Document, ctx: VenueContext) -> str:
    known = "\n".join(
        f"- {n} ({d or 'data desconhecida'})" for n, d in ctx.known_events
    ) or "- (nenhum)"
    partes = [
        _PROMPT_BASE,
        f"\nCONTEXTO:\n- Local: {ctx.venue_name or '?'} (@{ctx.handle or '?'})",
        f"- Hoje: {ctx.today_iso}",
        f"- Eventos futuros JA CONHECIDOS deste local:\n{known}",
        f"\nLEGENDA DO POST:\n{doc.caption or '(sem legenda)'}",
    ]
    return "\n".join(partes)


class PostInterpreter:
    def __init__(self, *, runner: Callable[[Path, str], str] | None = None,
                 retries: int = 1) -> None:
        self._runner = runner or run_codex
        self._retries = retries

    def interpret(self, doc: Document, ctx: VenueContext) -> PostInterpretation | None:
        base = build_prompt(doc, ctx)
        prompt = base
        for attempt in range(self._retries + 1):
            try:
                output = self._runner(doc.image_path, prompt)
                return PostInterpretation.model_validate(extract_json(output))
            except (ValueError, json.JSONDecodeError, ValidationError,
                    subprocess.SubprocessError, OSError) as exc:
                _log.warning("interpretacao de %s falhou (tentativa %d): %s",
                             doc.image_path, attempt + 1, exc)
                prompt = (base + "\n\nATENCAO: sua resposta anterior foi invalida "
                          f"({exc}). Responda APENAS com o objeto JSON.")
        return None
