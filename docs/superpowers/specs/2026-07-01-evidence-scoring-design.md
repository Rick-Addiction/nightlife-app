# Nightlife App — Score derivado da evidência (+ idempotência) — Design (Spec)

- **Data:** 2026-07-01
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** Revisão de design pós-esqueleto identificou que 4 promessas do spec principal (§3, §7) estão mortas no código, todas pela mesma causa raiz: **a confiança é um snapshot calculado na escrita a partir dos sinais de UM ingest**, em vez de derivada da evidência acumulada. Este refactor corrige a causa raiz **antes** da primeira fonte real (OSM), porque cada fonte nova amplia o débito.

---

## 1. Problema

| Promessa (spec principal) | Estado atual |
|---|---|
| §7 evento: **+20 se 2+ fontes independentes** | nunca dispara — sinais derivados por ingest não veem evidência acumulada |
| §7 venue: **+15 se evento futuro linkado** | nunca dispara — nada liga eventos ao score do venue |
| §7 **decay temporal** (freshness) | não implementado — `max()` no merge cria um ratchet: score só sobe |
| §3 **reprocessar só o que mudou** (`raw_payload_hash`) | cada re-execução de fonte insere linha de evidência idêntica (N runs = N linhas iguais) |

Smell relacionado: `confidence_contribution` guarda o score **total** da entidade no momento da escrita, não a contribuição daquela fonte — o nome mente.

## 2. Solução — visão geral

**A evidência (`venue_sources`/`event_sources`) vira a fonte da verdade do score.** Depois de gravar/atualizar a evidência, o repositório **recomputa** a confiança a partir de tudo que está acumulado. O frescor (decay) é um fator aplicado **na leitura** (API), não um job.

Consequências: o bônus multi-fonte e o `future_event_linked` passam a disparar naturalmente; o decay não precisa de cron; re-tunar pesos não exige backfill; `verification_logs` ganha escritor (trilha de mudanças de score).

## 3. Mudanças por componente

### 3.1 Idempotência de evidência (repos)
Ao gravar evidência, procurar linha existente por **(entity_id, source_type, source_url)** — `source_url=None` conta como valor de chave:
- existe → atualiza `last_seen_at`, `fetched_at`, e `raw_payload_hash`/`extracted_fields` se mudaram;
- não existe → insere.

Re-executar a mesma fonte N vezes mantém 1 linha por evidência (com `last_seen_at` fresco).

### 3.2 Novo módulo `persistence/confidence.py`
Substitui `ingestion/signals.py` (que é **deletado** — o mapeamento source_type→sinal passa a viver aqui, olhando evidência acumulada):

- `venue_signals_from_evidence(session, venue, *, reference) -> VenueSignals`:
  - `google_places_operational` / `osm_match` / `official_website` / `instagram_link` ← existe evidência com o respectivo `source_type`;
  - `future_event_linked` ← existe `Event` com `venue_id=venue.id` e `starts_at >= reference`;
  - `closed` / `permanently_closed` ← `venue.status`;
  - `stale` / `unverified` ← **False no v1** (frescor é decay na leitura; documentado).
- `event_signals_from_evidence(session, event, *, reference) -> EventSignals`:
  - `future_date` / `past_date` ← `starts_at` vs `reference`;
  - `venue_matched` / `no_venue` ← `venue_id`;
  - `official_source` ← evidência com source_type em `("official_website", "organizer")`;
  - `ticketing_source` ← evidência `"ticketing"`;
  - `independent_source_count` ← `COUNT(DISTINCT source_type)` da evidência (proxy de independência: 2 posts do mesmo IG **não** contam como 2 fontes);
  - `cancelled` ← `event.status`; `ambiguous_date`/`weak_source` ← False no v1.
- `recompute_venue_confidence(session, venue, *, reference) -> int` e `recompute_event_confidence(session, event, *, reference) -> int`: derivam sinais → `score_venue`/`score_event` (domínio puro, **inalterado**) → gravam em `entity.confidence`; se o valor mudou, inserem `VerificationLog(entity_type, entity_id, note="confidence {old} -> {new} (recompute)")`.
- Pesos standalone por fonte para `confidence_contribution` (agora honesto — "quanto esta fonte vale sozinha"): venues `{google_places:30, osm:20, official_website:20, instagram:15}`, events `{ticketing:25, official_website:25, organizer:25}`, demais 0.

### 3.3 Assinaturas dos repos (breaking interno)
- `upsert_venue(session, candidate, source, *, reference: date) -> Venue`
- `upsert_event(session, candidate, source, *, reference: date) -> Event`

O parâmetro `signals` **some** (era o snapshot). Fluxo: match/dedupe → cria ou reusa entidade → evidência idempotente (§3.1) → `recompute_*` (§3.2). O `max()` de merge some — recompute substitui (score pode **descer** se, p.ex., o evento passou ou foi cancelado; é o comportamento certo).

### 3.4 Faixa de "review" no venue matching (repo)
Merge automático de venue errado envenena a âncora de todos os eventos. Espelhar o padrão dos eventos, no `upsert_venue`:
- melhor match (via `match_venue(..., threshold=0.0)` — domínio inalterado) e `classify_venue_match(score)` novo em `domain/matching.py` (puro):
  - `>= 0.85` → **auto_merge** (reusa venue);
  - `0.70–0.85` → **cria novo** + `DedupeCandidate(kind="venue", decision="review")`;
  - `< 0.70` → distinto.
- `_resolve_venue` do pipeline (âncora de evento) continua usando `match_venue` com threshold atual (0.82) — anchoring não tem faixa de review.

### 3.5 Decay na leitura (domínio + API)
- `domain/freshness.py` (puro): `freshness_factor(last_seen_at, now) -> float` — `1.0` até 30 dias; decai linearmente até `0.5` aos 180 dias; piso `0.5`.
- API: `effective_confidence = round(confidence * freshness_factor(last_seen_at, now))` calculado por linha (volume pessoal). Filtro `min_confidence` passa a valer sobre o **effective** (pré-filtro SQL por `confidence >= min` continua válido, pois `effective <= stored`). Schemas ganham `effective_confidence`; ordenação de venues por effective desc.

### 3.6 Defaults da API de eventos
`GET /events` sem `date_from` passa a assumir `date_from = hoje`; parâmetro novo `include_past=true` desliga o default. (Alinha com a penalidade de `past_date` e evita a lista acumular passado eternamente.)

## 4. O que NÃO muda
- `domain/scoring.py` (a matemática pura), `domain/dedupe.py`, extração, modelos/**schema do banco** (nenhuma migration — colunas reusadas), fixtures, seed.
- `ingestion/pipeline.py` simplifica (não deriva mais sinais), mas o protocolo `Source` fica idêntico.

## 5. Testes
- Novos: idempotência (mesma fonte 2x → 1 linha de evidência, `last_seen_at` atualizado); multi-fonte (+20 dispara com 2 source_types distintos); `future_event_linked` (+15 no venue após evento futuro); recompute pode descer (evento cancelado); `freshness_factor` (bordas 30/180 dias, piso); faixa de review de venue (0.70–0.85 → DedupeCandidate); API `effective_confidence` e default upcoming.
- Atualizados: testes de repo/pipeline que usavam a assinatura antiga (`signals=`) e o teste `test_merge_keeps_highest_confidence` — a semântica nova correta é: places(30) + osm(20) acumulados = **50** (não "mantém 30").
- Suíte permanece offline/determinística (recompute recebe `reference`).

## 6. Sequenciamento
Este refactor é **pré-requisito da fonte OSM** (mesma frente de trabalho): a idempotência importa a partir da primeira re-execução real, e a faixa de review importa a partir do primeiro ingest de catálogo em massa.

## 7. Definition of Done
- [ ] Evidência idempotente por (entity, source_type, source_url).
- [ ] `confidence` recomputada da evidência acumulada em todo upsert; `verification_logs` registra mudanças.
- [ ] Bônus multi-fonte e `future_event_linked` disparam (testados).
- [ ] `ingestion/signals.py` removido; pipeline usa os repos novos.
- [ ] Faixa de review de venue match no `upsert_venue`.
- [ ] `freshness_factor` + `effective_confidence` na API; `/events` default upcoming.
- [ ] Suíte inteira verde.
