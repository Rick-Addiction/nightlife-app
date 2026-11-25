# NightLife · RADAR★SP

Backend pessoal que descobre, verifica, deduplica e expõe **venues e eventos** de vida noturna de São Paulo (baladas, festas, eventos, festivais) — com evidência, rastreio de fonte e score de confiança. O valor está na camada de dados confiável; a interface (lista + mapa) consome a API.

> Não busca 100% de cobertura: o sistema mede a própria cobertura, frescor e verificação. Respeita robots.txt / termos das fontes e não coleta dados pessoais de participantes.

## Arquitetura (4 camadas)

1. **Catálogo** — descobre venues (Google Places / OSM / listas) → `venues` com geo.
2. **Canais** — acha IG / site / ticketing de cada venue → `venue_sources`.
3. **Eventos** — extrai eventos dos canais monitorados (JSON-LD / HTML / flyer) → `events` ancorados no venue.
4. **Saída** — API REST (lista + mapa via bbox).

Camadas de código:
- `domain/` — lógica pura: datas PT-BR, scoring, matching, dedupe.
- `extraction/` — JSON-LD / HTML / texto livre → `ExtractedEvent`.
- `persistence/` — modelos SQLAlchemy + repositórios (`upsert_venue`, `upsert_event`).
- `ingestion/` — fontes + pipeline (`run_ingestion`).
- `api/` — FastAPI.

## Rodando

Requer Python 3.12+ e Docker.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Windows; Linux/mac: .venv/bin/python

docker volume create nightlife_pgdata               # cria o volume externo no primeiro uso
docker compose up -d --wait                        # Postgres+PostGIS (porta 5434)
.venv/Scripts/python -m alembic upgrade head       # cria o schema
.venv/Scripts/python -m nightlife.seed             # popula com dados mock
.venv/Scripts/python -m uvicorn nightlife.api.main:app --reload --port 8001
```

### Ingestão real

```bash
.venv/Scripts/python -m nightlife.ingest_osm      # baladas + casas de evento de SP (Overpass)
.venv/Scripts/python -m nightlife.ingest_sympla   # eventos de festas/shows de SP (Sympla)
.venv/Scripts/python -m nightlife.ingest_flyers   # flyers do inbox flyers/ (visao via codex CLI)
```

Flyers: jogue imagens (print de story, download de post) em `flyers/` e rode o
runner — a extração usa o Codex CLI da sua assinatura (custo marginal zero).
Processadas vão para `flyers/processed/`, falhas para `flyers/failed/`
(nenhuma imagem é extraída duas vezes).

Re-executar é seguro (matching reusa venues; evidência é idempotente). O runner
imprime quantos pares de venue caíram na fila de revisão (`dedupe_candidates`)
— material para calibrar os thresholds de matching com dados reais.

Endpoints: `GET /venues?type=&bbox=&min_confidence=`, `GET /events?date_from=&date_to=&bbox=&genre=&min_confidence=`, `GET /venues/{id}`, `GET /events/{id}`. `bbox` = `minLng,minLat,maxLng,maxLat`.

## Testes

```bash
docker compose up -d --wait
.venv/Scripts/python -m pytest -q -o console_output_style=count
```

## Como adicionar uma fonte

1. Implemente o protocolo `Source` em `ingestion/base.py`. Os métodos `venues()`, `event_pages()` e `events()` fornecem locais, páginas e eventos estruturados, respectivamente.
2. Confira em `persistence/confidence.py` como o tipo de fonte contribui para a confiança do registro.
3. Para um novo formato de página, adicione um ramo em `_extract_page` (`ingestion/pipeline.py`) reusando um extractor de `extraction/`.
4. Rode a fonte via `run_ingestion(session, sua_fonte, reference=...)`.

A fonte mock (`ingestion/mock_source.py` + `fixtures/`) é o exemplo de referência.

## Status

O RADAR★SP reúne locais e festas na interface Festas, Mapa e Locais. O catálogo cruza OpenStreetMap, Google Places, Resident Advisor, Sympla, Shotgun, agendas de casas e posts de Instagram. Na Baixa Augusta, a varredura por área ajudou a encontrar casas ausentes e a corrigir duplicatas.

Em 28 de outubro de 2026, a edição de Halloween reuniu **162 festas para 31 de outubro**, das quais 91 tinham tema de Halloween e 147 tinham local divulgado. [Agenda publicada](https://claude.ai/artifact/SqGwMGM13hraAuMkqbEdjV)

- [Especificações do produto](docs/superpowers/specs/) e [planos de implementação](docs/superpowers/plans/)
- [Primeiras explorações de interface](docs/design/interface-inicial/) e [pranchas do RADAR★SP](docs/design/radar-sp/)

## UI web (lista + mapa)

Requer Node 20+. Em dois terminais:

```bash
# 1. Backend (API em :8001)
docker compose up -d --wait
.venv/Scripts/python -m uvicorn nightlife.api.main:app --port 8001

# 2. UI (Vite em :5173, faz proxy de /api -> :8001)
cd web && npm install && npm run dev
```

Abra http://localhost:5173. Barra de filtros (data/gênero/confiança) dirige lista e mapa juntos; toggle "Só lista ↔ Lista + Mapa". Eventos sem venue geo aparecem na lista com selo "local a confirmar".

Testes da UI: `cd web && npm run test`.

## Instagram (descoberta de handles + scraper de flyers)

Requer Playwright: `.venv/Scripts/python -m pip install playwright && .venv/Scripts/python -m playwright install chromium`.

> Se o download do chromium falhar com `UNABLE_TO_VERIFY_LEAF_SIGNATURE` (Avast intercepta o TLS nesta máquina), rode o install com `NODE_TLS_REJECT_UNAUTHORIZED=0` só nesse comando — não persista a variável no ambiente.

```bash
# 1. Descobrir os @handles dos venues/organizers (tags OSM + sites + Sympla)
.venv/Scripts/python -m nightlife.discover_handles

# 2. Logar a conta BURNER (uma vez; janela do Chromium abre p/ login manual)
.venv/Scripts/python -m nightlife.ig_login

# 3. Varrer os perfis -> baixa flyers recentes (imagem + sidecar) pro inbox flyers/
.venv/Scripts/python -m nightlife.ingest_ig

# 4. Extrair os flyers baixados -> eventos no banco (pipeline de visao)
.venv/Scripts/python -m nightlife.ingest_flyers
```

Ritmo conservador (1x/dia, headful, delays humanos, caps em `config.py`). Use uma
conta **burner** (não a principal): o Instagram pode bloquear automação. Handles
com falhas repetidas são auto-pausados.

## Agendamento diário (Windows)

O coletor diário descobre perfis, coleta Resident Advisor, Sympla e Shotgun, geocodifica locais e processa flyers. O monitoramento do feed e a leitura dos sites têm tarefas próprias. [Coletor diário](src/nightlife/daily.py) · [Tarefas do feed e dos sites](scripts/register_feed_tasks.ps1)

```powershell
# registra a tarefa (uma vez; sem admin). Horario opcional (default 05:00):
powershell -ExecutionPolicy Bypass -File scripts\register_daily_task.ps1 -At 05:00
```

A tarefa roda só quando você está logado (o Chromium headless e o Codex CLI precisam da sua sessão); se o PC estiver desligado no horário, roda assim que possível no próximo logon. Log em `logs/daily.log`. Para rodar à mão: `.venv\Scripts\python -m nightlife.daily`. Para remover: `Unregister-ScheduledTask -TaskName NightlifeDaily -Confirm:$false`.
