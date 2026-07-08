# Nightlife App — Ciclo A: Identidade & vivacidade dos venues — Design (Spec)

- **Data:** 2026-07-07
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto (caso Selva):** o usuário notou que "Inferno Club" (R. Augusta 501, fechado há anos) aparecia no mapa e a **Selva Club** (o clube real no mesmo endereço desde 2017) não. Diagnóstico via sondas reais: (1) a semente do Places ficou a 1,2km do quarteirão — **nunca buscado**; (2) nosso `PlacesClient` não manda `languageCode` — a API serve o índice EN com o alias **velho** ("Inferno Club"); com `pt-BR`, o MESMO place_id retorna **"Selva Club"** (confirmado em Nearby e Details); (3) nunca pedimos `businessStatus` nem `websiteUri` (o record da Selva traz `https://selva.club/`). Números do banco: 1047 venues, 760 nightclubs, **535 só-RA-sem-evento** (fantasmas potenciais — o diretório do RA guarda clubes históricos e o RA ainda lista 28883 como "Inferno Club" hoje), só 53 multi-fonte. Dos 535 fantasmas, só **31 têm venue verificado pelo Google a ≤30m** (candidatos a fusão); o resto é clube morto sem record no Google — o mecanismo pra esses é não virar pin. **Decisão do usuário: nada de fixes manuais — tudo sistemático.**

---

## 1. Objetivo

O mapa mostrar só venues com sinal de vida, com nome atual e site oficial — automaticamente. No caso-teste: **a Selva aparece com nome certo e o Inferno é fundido nela, sem nenhuma intervenção manual.**

## 2. Decisões travadas (do brainstorming)

1. **Regra do pin = corroborado OU ativo.** Pin se: verificado pelo Places, OU 2+ fontes independentes, OU ≥1 evento, OU IG/site, OU monitorado. Só-RA-sem-nada → dormant (fica no banco, some do mapa, volta se ganhar corroboração). `CLOSED_PERMANENTLY` → nunca aparece.
2. **Reconciliação automática em duas regras** (mesmo passo, nesta ordem):
   - **Consolidação por nome:** par de venues a ≤30m com `name_similarity ≥ 0.70` e pelo menos um lado verificado pelo Places → `merge_venues` (caso "Kat Klub" do Places vs "Kat Klub São Paulo" do RA — sem isso a redescoberta criaria pins duplicados na faixa de review). Sustentado pela calibração histórica: os 26 falsos-positivos de nome estavam todos a >800m.
   - **Supersessão com trava dupla:** fantasma (**exatamente uma fonte ∈ {RA, OSM}**, 0 eventos) a ≤30m de **exatamente um** venue verificado → `merge_venues` (a identidade `ra.co/clubs/N`/`osm.org/...` migra pro sobrevivente → ingestões futuras ancoram certo). Cobre Inferno→Selva (RA) e Beco 203→Kat Klub (OSM, 18m). Ambiguidade (2+ candidatos ≤30m, ou nenhum ≤30m mas algum ≤60m) → fila de review.
   - Hoje: ~31 fusões RA + 2 OSM; cresce após a redescoberta densificada. Sobrevivente pela regra existente (`_pick_survivor`: maior confiança, empate → menor id); tudo auditável no `VerificationLog`.
3. **Cobertura por subdivisão automática.** Busca que satura (20 resultados) subdivide o círculo em 4 e re-busca, recursivo, com freios: raio mínimo 150m, profundidade máx 3. + ~6 sementes novas de corredores (Baixa Augusta/Consolação, Liberdade, Santa Cecília, Bom Retiro, Mooca, Ipiranga).
4. **Enrichment completo sob demanda.** Place Details por place_id: nome canônico pt-BR + `businessStatus` + `websiteUri`. Cache de 30 dias (`enriched_at`); ~US$8–14 por rodada completa de Details.
5. **Judgment calls aprovados:** (a) ter evidência do Places conta como vivo **antes** do Details rodar (senão os recém-descobertos sumiriam do mapa até o enrich); (b) o nome pt-BR do Places **sempre vence** (renomeia com trilha no `VerificationLog`, inclusive sobre OSM/RA); (c) freios da subdivisão: 150m / profundidade 3.

## 3. Arquitetura & fluxo

```
discover_places (atualizado)      enrich_places (NOVO)                  API /venues
Nearby pt-BR + businessStatus  →  1. Details: nome pt-BR (renomeia   →  venue_relevance v2:
no field mask; satura 20 →           com log) + websiteUri + status      pin só corroborado-
subdivide em 4 (recursivo);       2. Reconciliação: consolida pares      ou-ativo; CLOSED_
+6 sementes de corredores            ≥0.70 ≤30m verificados; supersede    PERMANENTLY nunca
                                     fantasmas; ambíguo → review          aparece
```

**Arquivos novos:**
- `src/nightlife/enrich_places.py` — runner sob demanda: `enrich_all` + `reconcile_venues` + `main`.
- `migrations/versions/xxxx_venue_business_status.py` — colunas `business_status` + `enriched_at` em `venues` (down_revision = `c3d4e5f6a7b8`).
- Testes novos: `tests/test_enrich_places.py`, `tests/test_reconcile.py`.

**Arquivos modificados:**
- `src/nightlife/ingestion/places_client.py` — `languageCode`, `businessStatus` no field mask, `PlaceDetails` + `place_details()`.
- `src/nightlife/ingestion/places_source.py` — subdivisão recursiva, sementes novas, filtra `CLOSED_PERMANENTLY` na descoberta.
- `src/nightlife/models.py` — 2 colunas novas em `Venue`.
- `src/nightlife/domain/nightlife_relevance.py` — `venue_relevance` v2.
- `src/nightlife/api/main.py` — computa e passa os sinais novos (query agrupada de contagem de fontes).
- Testes correspondentes. **Zero mudança no frontend** (o filtro é server-side).

## 4. Componentes

### 4A. `PlacesClient` (modifica)

- `search_nearby`: body ganha `"languageCode": "pt-BR"`; field mask ganha `places.businessStatus`; `PlaceResult` ganha `business_status: str | None`.
- **`place_details(place_id) -> PlaceDetails | None`** (novo): `GET https://places.googleapis.com/v1/places/{place_id}?languageCode=pt-BR`, field mask `id,displayName,businessStatus,websiteUri`. `PlaceDetails(name, business_status, website)` (frozen dataclass). Erro HTTP/rede/JSON/parse → `None` (retentável — não grava `enriched_at`, tenta no próximo run). Reusa o MESMO `httpx.Client` (lição Errno 24).

### 4B. `PlacesSource` (modifica) — subdivisão + sementes

- `venues()` passa a buscar por célula: `_search_cell(seed_name, lat, lng, radius, type, depth)`. Se retornar 20 (teto) E `radius/2 ≥ 150m` E `depth < 3`: **emite os 20** e subdivide em 4 sub-células com centros deslocados ±radius/2 (conversão metros→graus: `dlat = m/111320`; `dlng = m/(111320·cos(lat))`) e sub-raio `radius·0.72` (≈1/√2 com folga — união cobre o círculo original; sobreposição é inócua, o pipeline deduplica por place_id). Loga cada subdivisão.
- Resultados com `business_status == "CLOSED_PERMANENTLY"` são **descartados na descoberta** (não criam venue).
- `SEED_POINTS` ganha: `("Baixa Augusta/Consolacao", -23.5515, -46.6505)`, `("Liberdade", -23.5590, -46.6350)`, `("Santa Cecilia", -23.5405, -46.6535)`, `("Bom Retiro", -23.5270, -46.6430)`, `("Mooca", -23.5555, -46.5985)`, `("Ipiranga", -23.5920, -46.6100)`.

### 4C. Migration + model

`Venue` ganha `business_status: str | None` (String(30)) e `enriched_at: datetime | None` (DateTime tz). Migration `down_revision = 'c3d4e5f6a7b8'`.

### 4D. Runner `enrich_places` — `enrich_all(session, client, *, now, max_age_days=30) -> dict`

Alvo: venues com evidência `google_places` (place_id = `VenueSource.source_url`; se houver mais de um, usa o de `last_seen_at` mais recente). Pula quem tem `enriched_at` a menos de `max_age_days` (cache — não re-paga). Para cada um, `place_details`:
- `None` → conta em `errors`, **não** grava `enriched_at` (retenta no próximo run).
- `name` ≠ `venue.name` → renomeia + `VerificationLog(note="rename: '<velho>' -> '<novo>' (places)")`.
- `website` presente → sobrescreve `venue.website` (loga se mudou).
- `business_status` → coluna + mapeia `venue.status`: `OPERATIONAL→"operational"`, `CLOSED_TEMPORARILY→"closed"`, `CLOSED_PERMANENTLY→"permanently_closed"` (o scoring já penaliza esses status).
- `enriched_at = now`.
Retorna `{enriched, renamed, websites_set, closed_perm, closed_temp, skipped_cached, errors}`.

### 4E. `reconcile_venues(session, *, reference) -> dict` (no mesmo runner, roda após o enrich; duas regras, nesta ordem)

**Regra 1 — consolidação por nome** (mata pins duplicados da faixa de review):
- Para cada par de venues com geo a ≤0.03km, com `name_similarity ≥ 0.70` e **pelo menos um lado verificado** (evidência `google_places`, `business_status != "CLOSED_PERMANENTLY"`): `merge_venues` com survivor via `_pick_survivor` (maior confiança, empate → menor id). Ex.: "Kat Klub" (Places) + "Kat Klub São Paulo" (RA) → 1 venue.
- Pares na faixa mas a 30–60m → `DedupeCandidate` review (comportamento atual preservado; nada muda pra eles).

**Regra 2 — supersessão com trava dupla** (mata fantasmas renomeados):
- **Fantasma:** exatamente **uma** fonte E ela ∈ `{"ra", "osm"}` E 0 eventos (qualquer época) E tem geo.
- **Candidato:** venue com evidência `google_places` E `business_status != "CLOSED_PERMANENTLY"` E distância ≤ 0.03km.
- Exatamente 1 candidato → `merge_venues(survivor=candidato, loser=fantasma)` — a evidência RA/OSM migra → a identidade `ra.co/clubs/N` / OSM passa a ancorar no sobrevivente (ingestões futuras não ressuscitam o fantasma). Cobre Inferno→Selva e Beco 203→Kat Klub.
- 0 candidatos ≤30m mas ≥1 a ≤60m, OU 2+ candidatos ≤30m → `DedupeCandidate(kind="venue", decision="review")` (sem duplicar par existente).
- Senão → nada (fica dormant pela regra do pin).

Idempotente (venue fundido deixa de existir; re-rodar não re-encontra). Retorna `{consolidated, superseded, review_queued, untouched}`.

`main()`: exige `GOOGLE_MAPS_API_KEY` (aborta claro), `truststore`, `enrich_all` + `supersede_ghosts`, commit único, imprime o report combinado, `sys.exit(1)` se o run falhar.

### 4F. `venue_relevance` v2 + API

```python
def venue_relevance(name, category, has_events, is_monitored, *,
                    places_verified=False, business_status=None,
                    source_count=1, has_contact=False) -> str:
    # blocked tem precedência: buffet (como hoje) OU fechado em definitivo
    if is_buffet_name(name) or business_status == "CLOSED_PERMANENTLY":
        return "blocked"
    if has_events or is_monitored:
        return "relevant"                       # atividade vence sempre
    alive = places_verified or source_count >= 2 or has_contact
    if category == "nightclub" and alive:
        return "relevant"
    return "dormant"
```

`api/main.py` (`list_venues`): computa por venue — `places_verified` (existe `VenueSource google_places`), `source_count` (COUNT DISTINCT source_type, uma query agrupada), `has_contact` (`instagram` ou `website` não-nulos), `business_status` (coluna) — e passa pra função. `include_all=True` continua devolvendo tudo (escape hatch de debug já existente). Estimativa do mapa hoje: ~200–250 pins; cresce com a redescoberta.

**Efeito colateral intencional:** venues **só-OSM sem evento** (ex. Beco 203 hoje) também caem em dormant — OSM sozinho não distingue vivo de morto. É auto-corretivo: a redescoberta densificada dá record do Places aos que existem de verdade (`places_verified` → voltam ao mapa); os mortos do OSM ficam dormant, que é o comportamento certo.

## 5. Autoridade de nomes

Ranking: **Places pt-BR > OSM/RA/qualquer outro** (neste ciclo; o site oficial entra acima no Ciclo B). Renomear melhora o matching futuro (o nome canônico casa melhor com novas fontes). Toda renomeação é auditável no `VerificationLog`.

## 6. Não-objetivos (YAGNI)

- Extração de handle do IG a partir do site (**Ciclo B** — o `websiteUri` deste ciclo é o elo).
- Mudanças de frontend (**Ciclo C**); interface da fila de review.
- Grade completa da RMSP; re-verificação agendada (runners são sob demanda; agendar é decisão futura).
- Tocar OSM/Sympla/IG sources.
- Fix manual de qualquer venue (decisão explícita do usuário).

## 7. Custos & segurança

- Rodada completa de smoke: redescoberta com subdivisão ~150–350 chamadas Nearby (~US$5–11) + Details ~400–700 (~US$8–14) ≈ **US$15–25, uma vez**. Depois, cache de 30d segura o custo das re-rodadas.
- `GOOGLE_MAPS_API_KEY` via env (existente). A chave atual foi exposta no chat — **rotacionar/restringir** segue recomendado; o código nunca a loga.

## 8. Testes

- **Cliente:** `languageCode` presente no body do Nearby e do Details; `businessStatus` no field mask; `place_details` parse OK / campos faltando / erro → `None`; um único `httpx.Client`.
- **Subdivisão:** 20 resultados dispara subdivisão (emite os 20 + busca 4 sub-células); respeita raio mínimo e profundidade; célula não-saturada não subdivide; `CLOSED_PERMANENTLY` descartado na descoberta; sementes novas presentes.
- **Enrich (DB):** renomeia com `VerificationLog`; seta website/status/coluna; `enriched_at` recente → pula (0 chamadas); Details `None` → não grava `enriched_at`; mapeamento dos 3 business_status.
- **Reconciliação (DB):** consolidação: par ≥0.70 a ≤30m com um lado verificado → funde ("Kat Klub"-like); par 30–60m → review, não funde; par ≥0.70 sem lado verificado → intocado. Supersessão: caso Inferno-like (fantasma RA + 1 verificado a 15m) → funde, evidência RA migra; fantasma só-OSM (Beco 203-like) → funde; 2 candidatos ≤30m → review; fantasma com evento → intocado; 40m → review; idempotência (re-run após merges não re-processa).
- **Relevância v2 (puro):** um caso por sinal; buffet e `CLOSED_PERMANENTLY` têm precedência; só-RA-sem-nada → dormant; evento vence tudo.
- **API (DB):** `/venues` esconde só-RA-sem-nada; mostra places-verified; `include_all` devolve tudo.
- Suítes verdes (pytest + Vitest intactos). **Smoke real:** redescoberta densa + enrich + reconciliação → **Selva Club renomeada automaticamente, Inferno fundido nela, Beco 203 fundido no Kat Klub, e UM só Kat Klub no mapa**, report completo, contagem de pins antes/depois, re-run do enrich → `skipped_cached` (0 custo).

## 9. Definition of Done

- [ ] `languageCode: pt-BR` + `businessStatus` no Nearby; `place_details` no cliente; testados.
- [ ] Subdivisão automática com freios (150m/3) + 6 sementes novas; `CLOSED_PERMANENTLY` filtrado; testados.
- [ ] Migration `business_status`/`enriched_at` aplicada; model atualizado.
- [ ] `enrich_places`: renomeia com log, seta site/status, cache 30d, erros retentáveis; testado.
- [ ] `reconcile_venues`: consolidação (≥0.70/≤30m/verificado) + supersessão (trava dupla, fantasmas RA e OSM), merges auditáveis, ambiguidade → review, idempotente; testado.
- [ ] `venue_relevance` v2 + sinais na API; testados.
- [ ] Suítes verdes; smoke real: **Selva renomeada + Inferno fundido + Beco 203 fundido no Kat Klub (um pin só) — tudo sem intervenção manual**, pins ~200–450, re-run com cache.
