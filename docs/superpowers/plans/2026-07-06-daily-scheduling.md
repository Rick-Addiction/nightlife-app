# Agendamento diário (Windows Task Scheduler) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um orquestrador `nightlife.daily` que roda os 3 runners (discover_handles → ingest_ig → ingest_flyers) em sequência, best-effort com log, disparado 1x/dia pelo Windows Task Scheduler (headless, sessão logada).

**Architecture:** Spec: `docs/superpowers/specs/2026-07-06-daily-scheduling-design.md`. Núcleo `run_daily(steps, *, run, log)` com executor injetável (testável sem subprocess/rede). Executor real via `subprocess.run` (isolamento + timeout por passo). `main()` monta log em arquivo+stdout e exit-code. `scripts/daily.bat` (headless env + venv) é o que o Task Scheduler chama; `scripts/register_daily_task.ps1` registra a tarefa.

**Tech Stack:** Python 3.14 (`subprocess`, `dataclasses`), pytest; Windows Task Scheduler (`Register-ScheduledTask`), batch.

**Convenções:**
- **cwd do shell RESETA entre chamadas Bash** — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Python: `.venv/Scripts/python`. Testes: `.venv/Scripts/python -m pytest ... --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife` (SEMPRE esse basetemp). A linha "N passed" pode não aparecer no pipe nesta máquina (artefato de `\r`) — confie no exit code (`echo $?`).
- Suíte backend hoje = **147**. Commits terminam com trailer `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`.
- **NÃO** mexa em `web/`.

---

## File Structure

```
src/nightlife/daily.py            # NOVO — orquestrador (core injetavel + executor real + main)
scripts/daily.bat                 # NOVO — wrapper headless que o Task Scheduler chama
scripts/register_daily_task.ps1   # NOVO — registra a tarefa diaria
.gitignore                        # MODIFICA — + logs/
README.md                         # MODIFICA — secao de agendamento
tests/test_daily.py               # NOVO
```

---

## Task 1: Núcleo `run_daily` (executor injetável)

**Files:** Create `src/nightlife/daily.py`; Create `tests/test_daily.py`

- [ ] **Step 1: Teste que falha** — crie `tests/test_daily.py`:

```python
from nightlife.daily import StepResult, run_daily, any_failed


def test_run_daily_roda_em_ordem_e_agrega():
    calls = []
    logs = []

    def fake_run(name, argv):
        calls.append(name)
        return StepResult(name=name, ok=True, output=f"out-{name}")

    steps = [("a", ["x"]), ("b", ["y"]), ("c", ["z"])]
    results = run_daily(steps, run=fake_run, log=logs.append)
    assert calls == ["a", "b", "c"]
    assert [r.name for r in results] == ["a", "b", "c"]
    assert not any_failed(results)


def test_run_daily_isola_falha():
    calls = []

    def fake_run(name, argv):
        calls.append(name)
        return StepResult(name=name, ok=(name != "b"))   # b falha

    results = run_daily([("a", ["x"]), ("b", ["y"]), ("c", ["z"])],
                        run=fake_run, log=lambda m: None)
    assert calls == ["a", "b", "c"]              # c roda mesmo com b falhando
    assert any_failed(results)
    assert [r.ok for r in results] == [True, False, True]


def test_run_daily_loga_por_passo():
    logs = []
    run_daily([("a", ["x"])], run=lambda n, a: StepResult(n, True), log=logs.append)
    assert any("a" in m for m in logs)
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_daily.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — módulo `daily` não existe.

- [ ] **Step 3: Implementar** — crie `src/nightlife/daily.py` (só o núcleo por ora):

```python
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
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_daily.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (3).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/daily.py tests/test_daily.py && git commit -m "feat(daily): run_daily — orquestracao best-effort com executor injetavel

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: Executor real (subprocess) + `main`

**Files:** Modify `src/nightlife/daily.py`; append em `tests/test_daily.py`

- [ ] **Step 1: Teste que falha** — em `tests/test_daily.py`, ADICIONE ao final:

```python
import sys
from nightlife.daily import _run_step


def test_run_step_ok():
    r = _run_step("echo", [sys.executable, "-c", "print('oi')"])
    assert r.ok is True
    assert "oi" in r.output


def test_run_step_falha_em_returncode_nao_zero():
    r = _run_step("fail", [sys.executable, "-c", "import sys; sys.exit(3)"])
    assert r.ok is False


def test_run_step_erro_ao_iniciar():
    r = _run_step("nope", ["programa_que_nao_existe_xyz_123"])
    assert r.ok is False
    assert "erro ao iniciar" in r.output
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_daily.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `_run_step` não existe.

- [ ] **Step 3: Implementar** — em `src/nightlife/daily.py`, adicione os imports no topo (junto do que já existe) e o código ao final:

Imports (topo, após os existentes):
```python
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
```

Código (final do arquivo):
```python
STEP_TIMEOUT = int(os.environ.get("DAILY_STEP_TIMEOUT", "1200"))  # 20 min por passo

STEPS: list[tuple[str, list[str]]] = [
    ("discover_handles", [sys.executable, "-m", "nightlife.discover_handles"]),
    ("ingest_ig", [sys.executable, "-m", "nightlife.ingest_ig"]),
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
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_daily.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (6 — 3 do núcleo + 3 do executor).

Confirme também que o módulo importa:
`cd /d/MyProjects/nightlife-app && .venv/Scripts/python -c "import nightlife.daily; print('import ok')"`
Expected: `import ok`.

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/daily.py tests/test_daily.py && git commit -m "feat(daily): executor real (subprocess+timeout) + main (log arquivo/stdout + exit code)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: Scripts do Windows + gitignore

**Files:** Create `scripts/daily.bat`; Create `scripts/register_daily_task.ps1`; Modify `.gitignore`

- [ ] **Step 1: `.gitignore`** — adicione `logs/` (se ainda não estiver). Verifique e adicione:
```bash
cd /d/MyProjects/nightlife-app && grep -qxF "logs/" .gitignore || echo "logs/" >> .gitignore
```

- [ ] **Step 2: `scripts/daily.bat`** — crie `scripts/daily.bat` com EXATAMENTE:
```bat
@echo off
REM Roda o pipeline diario HEADLESS. E o que o Windows Task Scheduler chama.
set IG_HEADFUL=0
cd /d D:\MyProjects\nightlife-app
.venv\Scripts\python.exe -m nightlife.daily
```

- [ ] **Step 3: `scripts/register_daily_task.ps1`** — crie `scripts/register_daily_task.ps1` com EXATAMENTE:
```powershell
# Registra a tarefa diaria no Windows Task Scheduler (usuario atual, sem admin).
# Uso: powershell -ExecutionPolicy Bypass -File scripts\register_daily_task.ps1 -At 05:00
param([string]$At = "05:00")

$bat = Join-Path $PSScriptRoot "daily.bat"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`""
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask -TaskName "NightlifeDaily" -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Tarefa 'NightlifeDaily' registrada — diaria as $At (roda so quando logado)."
```

- [ ] **Step 4: Parse-check do PowerShell (não registra nada)** — garante que o `.ps1` é sintaticamente válido sem executá-lo. Use aspas SIMPLES no Bash (pra ele não tocar nos `$` do PowerShell):
```bash
cd /d/MyProjects/nightlife-app && powershell -NoProfile -Command '$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("scripts\register_daily_task.ps1",[ref]$null,[ref]$e); if($e){Write-Error "parse error"; exit 1} else {"ps1 ok"}'
```
Expected: `ps1 ok` (sem erro de parse). Se der erro de parse, corrija a sintaxe do `.ps1` (não registre a tarefa).

- [ ] **Step 5: Commit**
```bash
cd /d/MyProjects/nightlife-app && git add scripts/daily.bat scripts/register_daily_task.ps1 .gitignore && git commit -m "feat(daily): daily.bat (headless) + register_daily_task.ps1 (Task Scheduler) + gitignore logs/

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 4: Smoke do orquestrador + README

**Files:** Modify `README.md`

- [ ] **Step 1: Suíte inteira verde**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife -p no:cacheprovider; echo "exit: $?"`
Expected: `exit: 0` (153 = 147 + 6 novos).

- [ ] **Step 2: Smoke do orquestrador SEM os runners pesados** — roda `main()` com `STEPS` trocados por um passo trivial, provando o wiring (subprocess real + log + exit code) sem tocar discover/ig/flyers:
```bash
cd /d/MyProjects/nightlife-app && rm -f logs/daily.log && .venv/Scripts/python -c "
import sys, nightlife.daily as d
d.STEPS = [('smoke', [sys.executable, '-c', \"print('passo ok')\"])]
try:
    d.main()
except SystemExit as e:
    print('exit code:', e.code)
" && echo "--- logs/daily.log ---" && cat logs/daily.log`
Expected: imprime `=== daily start ===`, `smoke: ok`, `=== daily end — ok ===`, `exit code: 0`, e o `logs/daily.log` contém essas linhas com timestamp.

- [ ] **Step 3: README** — em `README.md`, ANEXE ao final (use Write/Edit, não echo):
```markdown
## Agendamento diário (Windows)

Roda `discover_handles` → `ingest_ig` → `ingest_flyers` 1x/dia (headless), via Windows Task Scheduler.

```powershell
# registra a tarefa (uma vez; sem admin). Horario opcional (default 05:00):
powershell -ExecutionPolicy Bypass -File scripts\register_daily_task.ps1 -At 05:00
```

A tarefa roda só quando você está logado (o Chromium headless e o Codex CLI precisam da sua sessão); se o PC estiver desligado no horário, roda assim que possível no próximo logon. Log em `logs/daily.log`. Para rodar à mão: `.venv\Scripts\python -m nightlife.daily`. Para remover: `Unregister-ScheduledTask -TaskName NightlifeDaily -Confirm:$false`.
```
(O bloco tem um ```powershell aninhado — ao anexar, preserve a cerca externa da seção e o fechamento do bloco interno; leia o final do README depois pra conferir as crases.)

- [ ] **Step 4: Commit**
```bash
cd /d/MyProjects/nightlife-app && git add README.md && git commit -m "docs: README do agendamento diario (register_daily_task.ps1 + logs/daily.log)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

- [ ] **Step 5 (MANUAL, fora deste plano):** o usuário registra a tarefa (`register_daily_task.ps1`) e faz 1 run real (`python -m nightlife.daily`, headless, com a burner) — verifica `logs/daily.log` e que flyers viram eventos. Task Scheduler/Playwright não rodam em pytest.

---

## Coverage map (plano ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §3 `run_daily` (ordem, best-effort, log) executor injetável | Task 1 |
| §3 executor real (subprocess+timeout) + main (log arquivo/stdout + exit code) | Task 2 |
| §4 `daily.bat` (headless) + `register_daily_task.ps1` (Task Scheduler) | Task 3 |
| §5 `logs/` gitignored | Task 3 |
| §6 suíte verde + smoke do orquestrador + README | Task 4 |

**Fora deste plano (spec §7):** notificação de resultado, cadência por-runner, retry automático, rotação de log.
