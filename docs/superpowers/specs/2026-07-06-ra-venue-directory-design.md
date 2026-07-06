# Nightlife App — Diretório de venues do RA — Design (Spec)

- **Data:** 2026-07-06
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** Estende a fonte RA (que já traz eventos). O RA-de-eventos só traz venues que têm programação futura; clubes sem evento (ex.: D-Edge nesta semana) não entram. Este passo semeia o **diretório de venues de SP do RA** — 684 clubes, incluindo D-Edge — direto no banco, independente de evento. É **1/3** do arco "mapa cheio de clubes" (as outras peças: Google Places p/ geo, e a UI pinar venues além de eventos).

---

## 1. Objetivo

Semear os venues de nightlife de SP do diretório do RA (`venues(areaId:400)`) no banco, via o pipeline existente, para que os clubes existam mesmo sem evento futuro — prontos para ancorar eventos e para quando geo (Places) + UI (pinar venues) chegarem.

## 2. Feasibilidade verificada (2026-07-06)

- Query `venues(areaId, orderBy: OrderByType!, limit, closed)` — `orderBy` é **obrigatório** (`LATEST`/`POPULAR`/`ALPHABETICAL`).
- **Quirk do `limit`, reproduzível:** com `orderBy:ALPHABETICAL` e **`limit ≤ 20`** a query retorna os **684** venues de SP; com `limit ≥ 50` retorna **0**. (O `limit` não capa a lista — pequeno traz tudo, grande quebra.) → usar `limit:20`.
- `area(id:400).venuesCount = 684`. Venue traz `id, name, address, contentUrl (/clubs/ID), eventCountThisYear, isClosed`, **sem geo** (`location`=0,0, como no RA-de-eventos).
- **Clubes que entram:** D-EDGE (`/clubs/4973`), Blitz Haus, Club Mono, Casa da Luz, etc. — maioria com `eventCountThisYear` baixo/0. **NÃO estão no RA:** Love Story, Selva, Warung (open-format/mainstream, fora do foco do RA).

## 3. Decisões travadas (do brainstorming)

- **Diretório agora (1/3 do arco).** Sozinho enriquece o banco, **não** enche o mapa (mapa é event-based + venues sem geo). Alinhado.
- Venues seedados com **`category="nightclub"`** (são nightlife; consistente com os venues de evento do RA) → viram `relevant` (mesmo sem geo/evento).
- **Roda junto no `ingest_ra` diário** (via `RASource.venues()`) — idempotente; sem runner separado.

## 4. Implementação

- **`parse_ra_venues(data) -> list[RawVenue]` (PURO)** em `ingestion/ra_source.py`: converte o resultado de `venues` em `RawVenue`s — `name`, `address`, `category="nightclub"`, `source_type="ra"`, `source_url="https://ra.co"+contentUrl`, **lat/lng = None**. Descarta: `isClosed=True`, nome vazio, nome TBA (`startswith("TBA")`, reusa a mesma heurística do `_venue_of`).
- **`RASource.venues()`** (hoje `[]`) passa a buscar o diretório: `venues(areaId:SP_AREA_ID, orderBy:"ALPHABETICAL", limit:20, closed:false)` via httpx (mesmo endpoint/headers de `events()`), e delega a `parse_ra_venues`. O `limit:20` é fixo com comentário explicando o quirk. Erro de rede/parse → propaga → `run_ingestion` marca o run com erro (padrão existente).
- O `ingest_ra` (já no `STEPS` do daily) passa a semear **venues do diretório + eventos** numa execução (o `run_ingestion` chama `source.venues()` e depois `source.events()`).

## 5. O que entra / não entra (via pipeline existente)

- Os ~684 venues são upsertados (`upsert_venue`): novos criados, os que casam com OSM/existente por nome deduplicam (preenche lacunas, +confiança multi-fonte). Evidência `VenueSource` com `source_type="ra"`.
- **Sem efeito visível imediato no mapa** (venues sem geo + sem evento → sem pin; o mapa da UI pina eventos). Aparecem quando: (a) ganham evento (o RA-de-eventos ancora), ou (b) Places geocoda + a UI passa a pinar venues.

## 6. Riscos & caveats (explícitos)

- **Dedup geoless amplificado:** 684 venues **sem geo** → mais chance de `auto_merge` falso só por nome com venues do OSM (a trava de distância pula quando `distance_km=None` — risco pré-existente do core, agora maior). Mitiga quando o Places geocodar. Não corrige o core aqui.
- **Perf:** 684 upserts/run, cada um carregando os venues p/ matching (O(n) por upsert) — aceitável no job diário (idempotente, dentro do timeout de 20min/passo).
- **Cobertura parcial:** Love Story/Selva/Warung não estão no RA — ficam pra outra fonte (Places/curado).

## 7. Testes

- **Puro (o grosso):** `parse_ra_venues` com fixture do shape real — venue normal (name/address/contentUrl → RawVenue nightclub sem geo, source_url `/clubs/ID`); `isClosed=True` → fora; nome TBA → fora; nome vazio → fora.
- **`RASource.venues()`** com httpx mockado — confirma que monta a query certa (`orderBy:ALPHABETICAL`, `limit:20`, `areaId`) e delega ao parse.
- **Smoke real:** `ingest_ra` traz os 684 venues (D-EDGE no banco) além dos eventos. Suíte segue verde (158 + novos).

## 8. Não-objetivos (YAGNI)

- Google Places / geocoding (próximo sub-projeto).
- UI pinar venues sem evento (peça 3/3 do arco).
- Runner separado (`ingest_ra_venues`) — roda junto no diário.
- Puxar venues fechados / de outras cidades / paginação além do `limit:20` (os 684 vêm de uma chamada).
- Corrigir o dedup geoless no core (registrado como risco; resolve com Places).

## 9. Definition of Done

- [ ] `parse_ra_venues` puro + testado (normal, closed, TBA, vazio).
- [ ] `RASource.venues()` busca o diretório (`ALPHABETICAL`, `limit:20`); testado com httpx mockado.
- [ ] `ingest_ra` (diário) semeia diretório + eventos.
- [ ] Suíte verde; smoke real (D-EDGE & cia. no banco).
