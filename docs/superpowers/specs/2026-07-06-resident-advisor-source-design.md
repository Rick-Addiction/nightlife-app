# Nightlife App — Fonte Resident Advisor (RA) — Design (Spec)

- **Data:** 2026-07-06
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** Ataca o gargalo de **cobertura** descoberto ao olhar a UI: os clubes de verdade de SP (D-Edge, Love Story, Supra, Selva...) **não estão no OSM** (verificado no Overpass), então o mapa fica vazio. O RA é o diretório de nightlife de verdade — traz venues geocodados + programação. Primeiro de dois sub-projetos de cobertura (o outro é Google Places, geocoding/enriquecimento, depois).

---

## 1. Objetivo

Uma fonte de ingestão `RASource` que consome a API GraphQL do Resident Advisor e traz os **eventos futuros de SP** (com o **venue embutido: nome + endereço**, sem geo — RA dá 0,0) para o banco, via o pipeline de ingestão que já existe. Enche a **lista** com a programação real dos clubes; o **mapa** ganha os venues que casam com o OSM (geo emprestado) e o resto quando o Google Places (próximo sub-projeto) geocodar os endereços.

## 2. Feasibilidade verificada (2026-07-06)

- `POST https://ra.co/graphql` responde **200 via httpx puro** (sem browser). As páginas HTML do RA são bloqueadas por Cloudflare (JS challenge), mas **o endpoint GraphQL não** — dá pra consumir como o Sympla.
- **Introspection ligada.** Campos de `Query` incluem `areas`, `area`, `eventListings`, `event`, `events`, `venue`, `venues`.
- **`Venue`** tem: `name`, `address`, `website`, `tba`, `isClosed`, `location`, `area`, ... **PORÉM** `location` volta **`{latitude:0, longitude:0}`** para os venues de SP (verificado no `eventListings` E no `venue(id)`) → **RA NÃO expõe geo utilizável**; o que é confiável é o **`address`** (ex.: "Rua Cardeal Arcoverde, 1479") + `website`. Alguns venues são **TBA** (nome = o endereço, `address: null`, flag `tba`).
- **`Event`** tem: `title`, `date`, `startTime`, `cost`, `venue`, `area`, `artists{name}`, `genres{name}`, `flyerFront`, `contentUrl` (ex.: `/events/2482976`). O `eventListings` já traz o venue embutido com `name`+`address`+`contentUrl` — **não precisa de query por-venue**.
- **`Area`**: `area(areaUrlName:"saopaulo", countryUrlCode:"br")` → **SP = id `400`** (74 eventos no probe). RA cobre inclusive **Baile Funk** (não é só eletrônica).

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
- `venue` = `RawVenue(name, lat=None, lng=None, address, category="nightclub", source_type="ra", source_url="https://ra.co"+venue.contentUrl)`. **Sem geo** (RA dá 0,0 → tratamos como ausente); o `address` é guardado. Venue **TBA** (contentUrl nulo / nome-é-endereço): ancora só pelo nome, sem criar lixo.
- `lineup_text` = join de `lineup`/`artists`; `genre` = 1º de `genres` (ou None); `ticket_url`/`source_url` = `contentUrl` (URL do evento no RA); `source_type="ra"`.
- `raw_payload` = JSON do registro (sort_keys, pra hash estável = idempotência da evidência).

## 5. O que desbloqueia (via pipeline existente, de graça)

- **Eventos reais de SP na lista** — o grande ganho: 74 eventos com data/line-up/gênero/venue, incluindo clubes que o OSM não tem.
- **Dedup multi-fonte + geo emprestado:** venue do RA casa com o do OSM (matching por nome já existe) → herda o **geo do OSM** (aí pina no mapa) e **soma confiança** (+20 multi-fonte). Venue do RA que NÃO casa (ex.: Fugaz Bar) fica sem geo → só na lista até ser geocodado.
- **Geo do resto vem do próximo sub-projeto (Google Places):** geocoda o `address` do RA → o Places agora tem um papel claro e necessário (RA dá endereço, não coordenada).
- **Relevância:** venue do RA vem com evento → `has_events` → `relevant`.
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
- **Google Places** (próximo sub-projeto — geocoda o `address` dos venues sem geo, incluindo os do RA).
- Scraping das páginas HTML do RA (Cloudflare) — o GraphQL basta.
- Filtro por gênero (RA já é nightlife; pega tudo de SP).

## 9. Definition of Done

- [ ] `ingestion/ra_source.py`: `RASource` + `parse_ra_events` puro; SP area resolvida/fixada; paginação com cap.
- [ ] `parse_ra_events` testado (venue com/sem geo, lineup, genre, passado, sem-título).
- [ ] Runner `python -m nightlife.ingest_ra`; `ingest_ra` no `STEPS` do daily.
- [ ] Probe de calibração pina área SP + shape do `eventListings`; fixture travada com dado real.
- [ ] Suíte verde; smoke real (clubes de SP geocodados no banco → pins no mapa).
