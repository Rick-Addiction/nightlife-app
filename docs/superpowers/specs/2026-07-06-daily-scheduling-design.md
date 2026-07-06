# Nightlife App — Agendamento diário (Windows Task Scheduler) — Design (Spec)

- **Data:** 2026-07-06
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** Fecha o roadmap operacional: rodar o pipeline de ingestão (descoberta de handles → scraper IG → extração de flyers) automaticamente 1x/dia, sem intervenção. Hoje os 3 runners são disparados à mão.

---

## 1. Objetivo

Um orquestrador `nightlife.daily` que roda os 3 runners em sequência, com log e isolamento de falha, disparado 1x/dia pelo **Windows Task Scheduler** (headless, na sessão logada do usuário).

## 2. Decisões travadas (do brainstorming)

- **Mecanismo:** Windows Task Scheduler (nativo, sobrevive reboot, roda na sessão logada — necessário pro Chromium/Codex).
- **Run agendado é headless** (`IG_HEADFUL=0`) — sem janelas pipocando; a sessão logada real da burner (cookies do login manual) mitiga o risco de detecção.
- **Os 3 runners rodam juntos, 1x/dia** (aceito rodar `discover_handles` diário mesmo sendo lento).
- **Só dispara com PC ligado + usuário logado**; se desligado, roda "assim que possível" no próximo logon (opção ligada).

## 3. Orquestrador `nightlife/daily.py`

- Sequência: `discover_handles` → `ingest_ig` → `ingest_flyers`.
- **Via subprocess** (isolamento — um `sys.exit`/crash num passo não derruba os outros): cada passo é `[sys.executable, "-m", "nightlife.<runner>"]`.
- **Best-effort:** falha de um passo é logada e o próximo roda mesmo assim.
- **Timeout por passo** (default 1200s = 20 min) — um browser travado não pendura o dia; timeout conta como falha do passo.
- **Log** com timestamp em `logs/daily.log` (append) e também no stdout (Task Scheduler captura). Cada passo loga início, fim, ok/falha, e (em falha) as últimas linhas da saída.
- **Exit code** != 0 se qualquer passo falhou (pro Task Scheduler mostrar "última execução: erro").

**Núcleo testável (executor injetável):**
```
run_daily(steps, *, run, log) -> list[StepResult]
```
- `steps`: lista de `(nome, argv)`.
- `run(argv, timeout) -> StepResult(name, ok, output)` — injetado; testes passam um fake que registra chamadas e simula ok/falha/timeout. A produção usa um executor baseado em `subprocess.run`.
- `log(msg)`: injetado/simples; testes capturam.
- Retorna a lista de `StepResult` (todos os passos, mesmo os que falharam).

`main()` monta o executor real + logging pra arquivo/stdout, chama `run_daily` com os 3 STEPS, imprime o resumo, e `sys.exit(0 se todos ok senão 1)`.

## 4. Ligação com o Windows

- **`scripts/daily.bat`** — o que o Task Scheduler chama. Wrapper fino: `set IG_HEADFUL=0`, `cd` pro projeto, roda `.venv\Scripts\python -m nightlife.daily`. (Batch, não PowerShell, pra o Task Scheduler chamar direto sem política de execução.)
- **`scripts/register_daily_task.ps1`** — registra a tarefa via `Register-ScheduledTask` (não exige admin p/ tarefa do usuário atual): gatilho **diário** num horário parametrizado (`-At`, default ex. 05:00), **`-LogonType Interactive`** / "run only when user is logged on", ação = o `daily.bat`, e `-StartWhenAvailable` (roda assim que possível se perdeu o horário). Imprime confirmação. **O usuário roda uma vez.**

## 5. Config

`logs/` (novo diretório, gitignored). O horário do agendamento é parâmetro do PS1 (não fica em `config.py` — é do Task Scheduler). O timeout por passo pode virar env (`DAILY_STEP_TIMEOUT`, default 1200) mas não é obrigatório expor.

## 6. Testes

- **Puro/injetável (o grosso):** `run_daily` — (a) chama os 3 passos na ordem; (b) **isolamento de falha**: se o passo 2 retorna falha, o passo 3 ainda é chamado e o resultado agrega a falha; (c) `main`/agregação: exit-code lógico (algum falhou → "erro"); (d) o `log` é chamado por passo. Executor fake injetado; sem subprocess real, sem rede.
- **Fora (smoke manual):** o `daily.bat`, o `register_daily_task.ps1`, e um run real `python -m nightlife.daily` (headless, com a burner) — verifica o log em `logs/daily.log` e o pipeline (flyers → eventos). Task Scheduler não roda em pytest (como o Playwright).
- Suíte backend segue verde (147 + novos).

## 7. Não-objetivos (YAGNI)

- Notificação de resultado (Telegram/email) — futuro.
- Cadência diferente por runner (por ora os 3 juntos, 1x/dia).
- Retry automático de passo que falhou (best-effort; o próximo dia re-tenta).
- Rodar sem sessão logada (headful/Codex exigem sessão interativa — fora de escopo).
- Rotação/limpeza de log (append simples; se crescer, corta-se depois).

## 8. Definition of Done

- [ ] `nightlife/daily.py` com `run_daily` (executor injetável) testado (ordem, isolamento de falha, exit-code lógico, log por passo) + `main`.
- [ ] `scripts/daily.bat` (headless + venv) e `scripts/register_daily_task.ps1` (Task Scheduler diário, logged-on, StartWhenAvailable).
- [ ] `logs/` no `.gitignore`.
- [ ] Suíte verde; smoke manual documentado (registrar a tarefa + 1 run real).
- [ ] README: como registrar o agendamento e onde ver o log.
