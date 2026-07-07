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

## 3. O fix (core) — DUAS peças

O fix tem duas partes que se completam: (A) `classify` não funde sem geo; (B) `upsert_venue` reconhece o MESMO venue por `source_url` (idempotência), pra a peça A não duplicar a cada run.

### 3A. `classify_venue_match` (`domain/matching.py`)

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
- Ambos geocodados e a <1km: `auto_merge` (seguro, como hoje). Candidato **sem geo**: `review`/`distinct`, **nunca funde**. Não mexe em `match_venue`, `normalize_name`, thresholds nem no boost geo.

### 3B. Identidade por `source_url` em `upsert_venue` (`persistence/venues_repo.py`)

**Por que:** sem a peça A, um venue geoless re-casava consigo mesmo por nome (auto_merge) — idempotente. Com a peça A ele iria pra `review` e **criaria duplicata a cada ingest** (o `ingest_ra` diário multiplicaria os 684). Correção: **antes** do matching por nome, se já existe um venue com a evidência exata `(source.source_type, source.source_url)` (e `source_url` não é None), é o **MESMO** venue — reusa (atualiza `last_seen`, preenche lacunas, grava evidência idempotente), sem criar nada nem classificar. Só quando NÃO há esse `source_url` conhecido é que roda o matching por nome/geo + `classify` (aí geoless → review).

```python
# no inicio de upsert_venue, antes do match_venue:
if source.source_url:
    known = session.scalars(
        select(Venue).join(VenueSource).where(
            VenueSource.source_type == source.source_type,
            VenueSource.source_url == source.source_url,
        )
    ).first()
    if known is not None:
        # mesmo (source_type, source_url) -> mesma venue (idempotente, independe de geo)
        ... (preenche lacunas geo/addr/cat, record_venue_evidence, recompute, return known)
```

`source_url` é identidade estável por fonte (RA `/clubs/ID`, OSM `osm.org/{type}/{id}`, Sympla a URL do evento). Isso torna re-ingest idempotente **independente de geo** — e é mais robusto que o auto_merge-por-nome que fazia esse papel antes.

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

- **`classify_venue_match` (puro):** geoless + score≥merge → `"review"` (NÃO `auto_merge`); geoless + score entre review e merge → `"review"`; geoless + score<review → `"distinct"`; ambos-geo + perto + score≥merge → `"auto_merge"` (inalterado); ambos-geo + longe → `"distinct"` (inalterado).
  - **Ajustar** `test_classify_venue_match_bands` (em `test_matching.py`): hoje chama `classify_venue_match(0.90)` sem distância → agora isso é geoless → `"review"`. Passar a testar as faixas COM geo (`distance_km=0.3`).
- **Identidade por source_url (`upsert_venue`, DB):** venue geoless re-ingerido com o MESMO `(source_type, source_url)` → **1 venue** (idempotente, evidência não duplica). Venue geoless com `source_url` NOVO cujo nome casa um existente → `review` (cria 2º venue + `DedupeCandidate`, não funde). Verificar que `test_rerun_same_source_is_idempotent` (geoless) segue verde **por causa** da identidade por source_url.
- **`repair_ra_dedup` (DB):** seed = venue OSM + evidência RA falsa nele + venue RA-only + evento RA-only + evento multi-fonte (RA+outra) → depois do `repair`: evidência RA some, venue RA-only some, evento RA-only some; o venue OSM e o evento multi-fonte **sobrevivem**.
- Suíte backend verde. Smoke real: rodar o `repair_ra_dedup` + `ingest_ra`; confirmar que "mono"/"sao paulo" viram venues separados (sem colapso) e que re-rodar `ingest_ra` **não** duplica (idempotente por source_url).

## 6. Não-objetivos (YAGNI)

- Mudar `normalize_name`/stopwords (o fix não depende).
- Re-dedup automático quando o Places geocodar (do sub-projeto Places — aí os duplicados geoless resolvem).
- O path de âncora de flyer (`_resolve_venue` no pipeline, outro fluxo — usa `match_venue`, não `classify`; fora de escopo).
- Interface de revisão dos `DedupeCandidate` (a fila já existe; consumi-la é outro tema).

## 7. Definition of Done

- [ ] **3A** `classify_venue_match`: sem geo → nunca `auto_merge` (review/distinct); testado (5 casos); `test_classify_venue_match_bands` ajustado p/ testar com geo.
- [ ] **3B** `upsert_venue`: identidade por `(source_type, source_url)` antes do matching por nome → re-ingest geoless é idempotente; testado.
- [ ] `repair_ra_dedup` apaga só dados RA (re-derivável); testado (OSM/multi-fonte sobrevivem).
- [ ] Suíte verde; smoke: repair + ingest_ra → "mono"/"sao paulo" separados, D-EDGE presente, re-run não duplica.
