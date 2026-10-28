# src/nightlife/daily.py
"""Orquestrador diario: roda os 3 runners em sequencia, best-effort, com log.

O nucleo `run_daily` recebe o executor (`run`) e o `log` injetados — testavel sem
subprocess/rede. O executor real (subprocess) e o main vem na Task 2.
Uso: .venv/Scripts/python -m nightlife.daily
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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
        try:
            result = run(name, argv)
        except Exception as exc:  # noqa: BLE001 — best-effort nao pode ser quebrado pelo executor
            result = StepResult(name=name, ok=False, output=f"erro inesperado: {exc}")
        log(f"{name}: {'ok' if result.ok else 'FALHA'}")
        results.append(result)
    return results


def any_failed(results: "list[StepResult]") -> bool:
    return any(not r.ok for r in results)


STEP_TIMEOUT = int(os.environ.get("DAILY_STEP_TIMEOUT", "1200"))  # 20 min por passo

STEPS: list[tuple[str, list[str]]] = [
    ("discover_handles", [sys.executable, "-m", "nightlife.discover_handles"]),
    ("ingest_ra", [sys.executable, "-m", "nightlife.ingest_ra"]),
    ("ingest_sympla", [sys.executable, "-m", "nightlife.ingest_sympla"]),
    ("ingest_shotgun", [sys.executable, "-m", "nightlife.ingest_shotgun"]),
    ("geocode_venues", [sys.executable, "-m", "nightlife.geocode_venues"]),
    ("ingest_flyers", [sys.executable, "-m", "nightlife.ingest_flyers"]),
]

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "daily.log"


def _run_step(name: str, argv: list[str]) -> StepResult:
    """Executor real: roda o argv em subprocess (isolado), com timeout por passo."""
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=STEP_TIMEOUT,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return StepResult(name=name, ok=(proc.returncode == 0), output=output)
    except subprocess.TimeoutExpired:
        return StepResult(name=name, ok=False, output=f"timeout apos {STEP_TIMEOUT}s")
    except OSError as exc:
        return StepResult(name=name, ok=False, output=f"erro ao iniciar: {exc}")


def _make_logger() -> Logger:
    LOG_DIR.mkdir(exist_ok=True)

    def log(msg: str) -> None:
        line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}"
        print(line, flush=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    return log


def main() -> None:
    log = _make_logger()
    log("=== daily start ===")
    results = run_daily(STEPS, run=_run_step, log=log)
    for r in results:
        if not r.ok:
            tail = "\n".join(r.output.splitlines()[-15:])
            log(f"saida de {r.name} (ultimas linhas):\n{tail}")
    failed = any_failed(results)
    log(f"=== daily end — {'ERRO' if failed else 'ok'} ===")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
