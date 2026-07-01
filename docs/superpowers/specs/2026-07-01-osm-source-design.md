# Nightlife App — Fonte real #1: OpenStreetMap / Overpass — Design (Spec)

- **Data:** 2026-07-01
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** Primeira fonte real do nightlife-app (o walking skeleton A→D já está no `master`). Substitui/complementa a fonte mock com venues reais de São Paulo.

---

## 1. Objetivo

Implementar a primeira **fonte real de venues**: consultar o OpenStreetMap (via Overpass API) e trazer baladas e casas de evento de São Paulo para o banco, através do pipeline de ingestão já existente (`run_ingestion`). Grátis, sem cadastro, e prova o caminho *fonte-real → banco*.

## 2. Escopo

### No escopo
- Uma fonte `OSMSource` que implementa o protocolo `Source` (`ingestion/base.py`).
- Categorias OSM: **`amenity=nightclub`** (baladas) + **`amenity=events_venue`** (casas de evento/festa/festival).
- Só **venues** — `event_pages()` retorna `[]` (OSM não tem eventos).
- Um runner (`ingest_osm.py`) que roda a fonte contra o banco real, espelhando o `seed.py`.
- `parse_overpass` como função pura, testada offline.

### Não-objetivos (YAGNI)
- Eventos (OSM não os tem).
- Outras categorias (bar/pub ficaram fora por decisão de escopo do projeto).
- Retry/backoff sofisticado, cache, paginação — uma query única de SP basta no volume pessoal.
- Deduplicação especial: o pipeline já faz venue matching via `upsert_venue`.

## 3. Arquitetura

`OSMSource` implementa `Source`. **I/O separado do parsing** para permitir teste offline:

- `parse_overpass(data: dict) -> list[RawVenue]` — **função pura**: recebe o JSON do Overpass e devolve `RawVenue`s. É o coração testável.
- `OSMSource.venues()` — faz o fetch HTTP no Overpass e delega a `parse_overpass`.
- `OSMSource.event_pages()` — retorna `[]`.

O fetch real é provado por smoke manual (runner), **não** no CI (evita teste dependente de rede).

Fluxo: `OSMSource` → `run_ingestion(session, source, reference)` → `upsert_venue` (com `derive_venue_signals("osm")` → sinal `osm_match`, score +20) → banco.

## 4. Componentes (arquivos)

- `src/nightlife/ingestion/osm_source.py` — `parse_overpass()` + classe `OSMSource`.
- `src/nightlife/ingest_osm.py` — runner: `OSMSource` → `run_ingestion` → commit → imprime contagens (espelha `seed.py`).
- `tests/test_osm_source.py` — testa `parse_overpass` com JSON fixo.

## 5. Query Overpass + mapeamento

**Bbox da cidade de SP** (south, west, north, east): `(-24.00, -46.83, -23.36, -46.36)`.

**OQL:**
```
[out:json][timeout:60];
(
  nwr["amenity"="nightclub"]({{bbox}});
  nwr["amenity"="events_venue"]({{bbox}});
);
out center tags;
```
(`nwr` = node/way/relation; `out center tags` traz o centro geométrico + as tags.)

**Fetch:** `httpx.post(endpoint, data={"data": query}, headers={"User-Agent": "nightlife-app/0.1 (pessoal)"}, timeout=90)`. Endpoint default: `https://overpass-api.de/api/interpreter`.

**Mapeamento** (por elemento do array `elements`):
| RawVenue | origem |
|---|---|
| `name` | `tags.name` — **descarta o elemento se ausente** |
| `lat` / `lng` | `lat`/`lon` (node) ou `center.lat`/`center.lon` (way/relation) |
| `address` | junta `addr:street` + `addr:housenumber` se houver, senão `None` |
| `category` | `tags.amenity` (`"nightclub"` ou `"events_venue"`) |
| `source_type` | `"osm"` |
| `source_url` | `https://www.openstreetmap.org/{type}/{id}` |
| `raw_payload` | `json.dumps(element)` |

Elementos sem coordenada utilizável (sem lat/lng nem center) também são descartados.

## 6. Testes

- **`test_parse_overpass`** (offline, sem rede): um JSON com (a) um `node` nightclub completo, (b) um `way` events_venue com `center`, (c) um elemento sem `name` → confirma o mapeamento correto de a/b e que c é descartado.
- **Smoke manual** (não CI): `python -m nightlife.ingest_osm` bate no Overpass real, popula o banco, e imprime `IngestionRun` + contagem de venues. Documentado no README.

Suíte automatizada permanece determinística e offline.

## 7. Dependências & boas práticas

- `httpx` migra de `[project.optional-dependencies].dev` para `dependencies` (agora é runtime).
- User-Agent identificado + timeout generoso no request — Overpass é um serviço gratuito compartilhado; respeito a rate limits e uso justo (volume pessoal = uma query esporádica).
- Se o Overpass falhar (timeout/HTTP erro), `venues()` propaga a exceção; o runner (`ingest_osm.py`) captura, marca o run com erro e reporta — não trava.

## 8. Definition of Done

- [ ] `parse_overpass` mapeia elementos Overpass → `RawVenue` corretamente (com descarte de sem-nome/sem-geo).
- [ ] `OSMSource` implementa `Source` (`venues()` faz fetch+parse; `event_pages()` = `[]`).
- [ ] `test_osm_source` passa (offline).
- [ ] `ingest_osm.py` roda contra o banco real e traz baladas de SP (smoke).
- [ ] README menciona como rodar a ingestão OSM.
