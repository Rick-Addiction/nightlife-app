# Nightlife App — Endurecer o dedup geoless — Design (Spec)

- **Data:** 2026-07-06
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** A code-review do diretório do RA **mediu** o dano do seed de venues sem geo: 14 venues colapsaram 2+ clubes distintos por `auto_merge` só-por-nome (a trava de distância do `classify_venue_match` é pulada quando `distance_km=None`; o `normalize_name` derruba stopwords → "Mono Club"/"Club Mono" viram ambos `"mono"` → score 1.0). Este passo estanca o sangramento (impede novos merges falsos) e limpa os já existentes. Pré-requisito antes de agendar o daily (que re-semeia).

---

## 1. Objetivo

Quando um candidato a venue **não tem geo** para confirmar que é o mesmo lugar físico, **nunca fazer `auto_merge`** — mandar pra `review` (cria venue novo + flag). E reparar os 14 colapsos já no banco, re-derivando os venues do RA (que são idempotentes).

## 2. Decisões travadas (do brainstorming)

- **Sem geo → nunca auto_merge → review** (opção segura; custo = duplicados que resolvem quando o Places geocodar). Não usar endereço como proxy (fuzzy demais), nem só threshold de nome (não resolve "mono"/"mono").
- **Reparar os 14 já colapsados** re-derivando o RA (apagar dados `source_type="ra"` + re-ingest). OSM/Sympla e eventos de flyer/IG **intactos**.

## 3. O fix (core, cirúrgico) — `domain/matching.py`

Uma mudança em `classify_venue_match(score, *, distance_km)`:

```python
def classify_venue_match(score, *, distance_km=None) -> str:
    if distance_km is not None and distance_km > MAX_DUPLICATE_DISTANCE_KM:
        return "distinct"                 # (igual) longe demais = lugares diferentes
    if distance_km is None:               # SEM GEO: nao da pra confirmar o lugar fisico
        return "review" if score >= VENUE_REVIEW_THRESHOLD else "distinct"
    if score >= VENUE_MERGE_THRESHOLD:
        return "auto_merge"               # so com geo verificado
    if score >= VENUE_REVIEW_THRESHOLD:
        return "review"
    return "distinct"
```

- Dois venues **ambos geocodados** e a <1km: `auto_merge` como hoje (seguro).
- Qualquer candidato **sem geo**: score alto → `review` (venue novo + `DedupeCandidate`), score baixo → `distinct`. **Nunca funde.** → zero merge falso novo.
- Não mexe em `match_venue`, `normalize_name`, thresholds, nem no boost geo. Só a árvore de decisão de `classify`.

**Interação com o pipeline:** `upsert_venue` (em `persistence/venues_repo.py`) já trata `review` criando venue novo + `DedupeCandidate`. Como os venues do RA são geoless, todos cairão em `review`/`distinct` (nunca `auto_merge`), criando venues separados. Custo aceito: duplicados (RA "Club Mono" ao lado do OSM "Mono Club") até o Places geocodar.

## 4. Reparar os 14 já colapsados — runner `repair_ra_dedup`

`src/nightlife/repair_ra_dedup.py` com `repair(session) -> dict` (contagens) + `main()`. Apaga **só** o que é do RA (re-derivável) e deixa o resto intacto. Ordem FK-safe:

1. `DELETE FROM event_sources WHERE source_type='ra'`.
2. `DELETE FROM events` que ficaram **sem nenhum EventSource** (eram RA-only; eventos multi-fonte sobrevivem).
3. `DELETE FROM venue_sources WHERE source_type='ra'`.
4. `DELETE FROM venues` que ficaram **sem nenhum VenueSource E sem nenhum Event** referenciando (RA-only órfãos; os venues do OSM/Sympla que absorveram evidência RA sobrevivem, agora limpos).
5. `DELETE FROM dedupe_candidates` (regeneram no próximo ingest).
6. commit; imprime quantos EventSource/Event/VenueSource/Venue removidos.

Depois (smoke, não no runner): re-rodar `python -m nightlife.ingest_ra` → re-cria os venues do RA como **separados** (com o fix) e re-ancora os eventos do RA.

## 5. Testes

- **Puro (o grosso):** `classify_venue_match` — geoless + score≥merge → `"review"` (NÃO `auto_merge`); geoless + score entre review e merge → `"review"`; geoless + score<review → `"distinct"`; ambos-geo + perto + score≥merge → `"auto_merge"` (inalterado); ambos-geo + longe → `"distinct"` (inalterado).
- **Ajustar** os testes existentes de `classify`/`upsert_venue`/`matching` que assumiam `auto_merge` para candidato sem geo (agora esperam `review`).
- **`repair_ra_dedup`:** com DB seedado (venue OSM + evidência RA falsa + venue RA-only + evento RA-only + evento multi-fonte) → depois do `repair`: evidência RA some, venue RA-only some, evento RA-only some, mas o venue OSM e o evento multi-fonte **sobrevivem**.
- Suíte backend verde. Smoke real: rodar o repair + `ingest_ra`; confirmar que "mono"/"sao paulo" viram venues separados (sem colapso).

## 6. Não-objetivos (YAGNI)

- Mudar `normalize_name`/stopwords (o fix não depende).
- Re-dedup automático quando o Places geocodar (do sub-projeto Places — aí os duplicados geoless resolvem).
- O path de âncora de flyer (`_resolve_venue` no pipeline, outro fluxo — usa `match_venue`, não `classify`; fora de escopo).
- Interface de revisão dos `DedupeCandidate` (a fila já existe; consumi-la é outro tema).

## 7. Definition of Done

- [ ] `classify_venue_match`: sem geo → nunca `auto_merge` (review/distinct); testado (5 casos).
- [ ] Testes existentes de classify/upsert/matching ajustados p/ a nova semântica geoless.
- [ ] `repair_ra_dedup` apaga só dados RA (re-derivável); testado (OSM/multi-fonte sobrevivem).
- [ ] Suíte verde; smoke: repair + ingest_ra → "mono"/"sao paulo" separados, D-EDGE ainda presente.
