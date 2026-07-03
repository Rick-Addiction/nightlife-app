# Nightlife App

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

docker compose up -d --wait                        # Postgres+PostGIS (porta 5434)
.venv/Scripts/python -m alembic upgrade head       # cria o schema
.venv/Scripts/python -m nightlife.seed             # popula com dados mock
.venv/Scripts/python -m uvicorn nightlife.api.main:app --reload --port 8001
```

### Ingestão real

```bash
.venv/Scripts/python -m nightlife.ingest_osm      # baladas + casas de evento de SP (Overpass)
.venv/Scripts/python -m nightlife.ingest_sympla   # eventos de festas/shows de SP (Sympla)
```

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

1. Implemente o protocolo `Source` (`ingestion/base.py`): métodos `venues()` e `event_pages()` devolvendo `RawVenue` / `RawEventPage`.
2. Mapeie o `source_type` em `ingestion/signals.py` para os sinais de scoring corretos.
3. Para um novo formato de página, adicione um ramo em `_extract_page` (`ingestion/pipeline.py`) reusando um extractor de `extraction/`.
4. Rode a fonte via `run_ingestion(session, sua_fonte, reference=...)`.

A fonte mock (`ingestion/mock_source.py` + `fixtures/`) é o exemplo de referência.

## Status

Esqueleto (walking skeleton) completo com dados mock: domínio + persistência + ingestão + API, com testes. Fontes reais (Places/OSM/ticketing/Instagram), extração multimodal de flyers, Telegram e a UI de lista/mapa são os próximos passos.
