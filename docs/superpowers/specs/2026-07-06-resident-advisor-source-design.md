# Nightlife App — Fonte Resident Advisor (RA) — Design (Spec)

- **Data:** 2026-07-06
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** Ataca o gargalo de **cobertura** descoberto ao olhar a UI: os clubes de verdade de SP (D-Edge, Love Story, Supra, Selva...) **não estão no OSM** (verificado no Overpass), então o mapa fica vazio. O RA é o diretório de nightlife de verdade — traz venues geocodados + programação. Primeiro de dois sub-projetos de cobertura (o outro é Google Places, geocoding/enriquecimento, depois).

---

## 1. Objetivo

Uma fonte de ingestão `RASource` que consome a API GraphQL do Resident Advisor e traz os **eventos futuros de SP** (com o **venue embutido, já geocodado**) para o banco, via o pipeline de ingestão que já existe. Enche o mapa/lista com a programação real dos clubes.

## 2. Feasibilidade verificada (2026-07-06)

- `POST https://ra.co/graphql` responde **200 via httpx puro** (sem browser). As páginas HTML do RA são bloqueadas por Cloudflare (JS challenge), mas **o endpoint GraphQL não** — dá pra consumir como o Sympla.
- **Introspection ligada.** Campos de `Query` incluem `areas`, `area`, `eventListings`, `event`, `events`, `venue`, `venues`.
- **`Venue`** tem: `name`, `location` (geo), `address`, `website`, `capacity`, `photo`, `contentUrl`, `area`, `topArtists`, `events`. → **venues do RA já vêm com lat/lng** (não dependem do Google Places).
- **`Event`** tem: `title`, `date`, `startTime`/`endTime`, `cost`, `venue`, `area`, `artists`, `lineup`, `genres`, `flyerFront`, `contentUrl`, `isFestival`.
- **`Area`** tem: `id`, `name`, `urlName`, `eventsCount`, `venuesCount` → SP resolvível por `urlName="saopaulo"`.

## 3. Decisões travadas (do brainstorming)

- Fonte **automática via httpx GraphQL** (não browser/Playwright).
- **SP inteiro, todos os gêneros** (RA já é 100% nightlife — sem filtro tipo o do Sympla).
- **Só eventos futuros** (a partir de hoje, dia SP) — coerente com o default da API/`/events`.
- **`ingest_ra` entra no orquestrador diário** (`nightlife/daily.py` STEPS), junto de discover/ig/flyers.
- Reusa o pipeline (`run_ingestion`) — **não toca no core** de scoring/dedupe/persistência.

## 4. `RASource` (`ingestion/ra_source.py`)

Mesma forma das fontes existentes (`Source` protocol: `venues()`/`event_pages()`/`events()`):
- `venues()` → `[]`, `event_pages()` → `[]` (venue vem embutido no evento, como no Sympla).
- `events()` → busca ao vivo:
  1. Resolve a **área de SP** (query por `urlName="saopaulo"` → `area.id`). O id pode ser fixado como constante após o probe e reconfirmado; se a query de área falhar, cai no id fixo.
  2. Pagina `eventListings(filters: {areas:{eq: SP_ID}, listingDate:{gte: hoje}}, pageSize, page)` até `max_pages` (cap) ou acabar.
  3. Delega o parse a `parse_ra_events(data, *, reference) -> list[RawEvent]` (**puro**).
- httpx POST com `truststore.inject_into_ssl()`, `User-Agent` + `Referer: https://ra.co/`, `Content-Type: application/json`, timeout. Erro de rede/parse → o `run_ingestion` marca o run com erro (padrão existente).

**`parse_ra_events` (puro, testável offline):** para cada evento, monta `RawEvent`:
- `name` = `title`; `starts_at` = parse de `date`/`startTime` (tz-aware); descarta sem `title` ou passado (dia SP).
- `venue` = `RawVenue(name, lat/lng do location, address, website, category="nightclub", source_type="ra", source_url=contentUrl)`. Venue sem `location` utilizável → venue sem geo (entra na lista, sem pin; geo pode vir do Places depois).
- `lineup_text` = join de `lineup`/`artists`; `genre` = 1º de `genres` (ou None); `ticket_url`/`source_url` = `contentUrl` (URL do evento no RA); `source_type="ra"`.
- `raw_payload` = JSON do registro (sort_keys, pra hash estável = idempotência da evidência).

## 5. O que desbloqueia (via pipeline existente, de graça)

- **Venues geocodados → pins no mapa** na hora (D-Edge, Love Story etc.).
- **Dedup multi-fonte:** venue do RA casa com o do OSM/Sympla (matching por nome/geo já existe) → preenche lacunas + **multi-fonte soma confiança** (+20).
- **Relevância:** venue do RA vem com evento → `has_events` → `relevant` (aparece no mapa/scraper).
- Evidência: `EventSource`/`VenueSource` com `source_type="ra"`, `source_url` = URL do RA.

## 6. Runners & integração

- `python -m nightlife.ingest_ra` (novo runner, padrão dos existentes: `truststore`, `SessionLocal`, `run_ingestion(session, RASource(...), label="ra")`, print de contagens).
- Adicionar `("ingest_ra", [sys.executable, "-m", "nightlife.ingest_ra"])` ao `STEPS` de `nightlife/daily.py` (antes do ig/flyers ou depois — ordem não crítica; sugerido logo após `discover_handles`).

## 7. Testes

- **Puro (o grosso):** `parse_ra_events` com fixtures do shape real do RA — evento com venue+geo; venue sem `location` (→ sem geo, mas presente); com/sem `lineup`; com/sem `genres`; evento passado descartado; sem `title` descartado. Paginação/cap testados no nível da fonte com httpx mockado (como o `test_sympla_source`).
- **Probe de calibração (implementação):** um passo que bate no RA real, pina a **área de SP** e o **shape exato** do `eventListings` (introspection ON facilita), e trava a fixture do parse com dados reais.
- **Smoke real:** `ingest_ra` puxa N eventos de SP → mostra venues+eventos criados (D-Edge & cia. no banco, geocodados).
- Suíte backend segue verde (154 + novos).

## 8. Não-objetivos (YAGNI)

- Páginas de artista/promoter do RA; ticketing/compra; presale.
- Cidades além de SP; backfill de eventos passados.
- **Google Places** (próximo sub-projeto — geocoding/enriquecimento p/ venues de OUTRAS fontes sem geo; RA já geocoda os dele).
- Scraping das páginas HTML do RA (Cloudflare) — o GraphQL basta.
- Filtro por gênero (RA já é nightlife; pega tudo de SP).

## 9. Definition of Done

- [ ] `ingestion/ra_source.py`: `RASource` + `parse_ra_events` puro; SP area resolvida/fixada; paginação com cap.
- [ ] `parse_ra_events` testado (venue com/sem geo, lineup, genre, passado, sem-título).
- [ ] Runner `python -m nightlife.ingest_ra`; `ingest_ra` no `STEPS` do daily.
- [ ] Probe de calibração pina área SP + shape do `eventListings`; fixture travada com dado real.
- [ ] Suíte verde; smoke real (clubes de SP geocodados no banco → pins no mapa).
