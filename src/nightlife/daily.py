# src/nightlife/daily.py
"""Orquestrador diario: roda os 3 runners em sequencia, best-effort, com log.

O nucleo `run_daily` recebe o executor (`run`) e o `log` injetados — testavel sem
subprocess/rede. O executor real (subprocess) e o main vem na Task 2.
Uso: .venv/Scripts/python -m nightlife.daily
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class StepResult:
    name: str
    ok: bool
    output: str = ""


Runner = Callable[[str, "list[str]"], StepResult]
Logger = Callable[[str], None]


def run_daily(steps: "list[tuple[str, list[str]]]", *, run: Runner, log: Logger) -> list[StepResult]:
    """Roda cada passo em sequencia, best-effort (falha de um NAO aborta os outros).
    `run(name, argv) -> StepResult`; `log(msg)`. Retorna todos os StepResult."""
    results: list[StepResult] = []
    for name, argv in steps:
        log(f"iniciando {name}")
        result = run(name, argv)
        log(f"{name}: {'ok' if result.ok else 'FALHA'}")
        results.append(result)
    return results


def any_failed(results: "list[StepResult]") -> bool:
    return any(not r.ok for r in results)
