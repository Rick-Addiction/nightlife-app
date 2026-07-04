# Nightlife App — Vision extractor de flyers (backend Codex) — Design (Spec)

- **Data:** 2026-07-03
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** Início do *moat* (roadmap item b): entender flyers — o formato dominante de divulgação de festa em SP. Decisão de backend: **CLI do Codex por assinatura** (`codex exec` headless, uso programático oficial), custo marginal zero, em vez de API paga. O "entender flyer" fica atrás de uma interface plugável; trocar de backend no futuro é escrever outro adapter.

---

## 1. Objetivo

Transformar uma imagem de flyer (print de story, download de post, foto) num `RawEvent` estruturado que entra no pipeline de ingestão existente — com contrato anti-alucinação, dedupe por conteúdo de imagem, e sem gastar cota à toa.

## 2. Fluxo

```
flyers/                      (pasta-inbox: o usuário joga imagens)
  → FlyerSource.events():
      1. dHash da imagem (dedupe por conteúdo; mesmo flyer 2x = 1 extração)
      2. CodexExtractor: codex exec headless com a imagem + prompt de extração
      3. JSON validado contra schema (1 retry se inválido); falha → pula imagem, loga erro
      4. RawEvent(source_type="vision_flyer", venue_name=..., sem venue embutido)
  → run_ingestion (pipeline padrão: resolução de venue, dedupe, score, evidência)
  → runner move a imagem para flyers/processed/ (não re-extrai, não re-gasta cota)
```

## 3. Escopo

### No escopo
- `FlyerExtractor` (Protocol) + `CodexExtractor` (subprocess `codex exec`).
- `FlyerSource` (implementa `Source`; `venues()`/`event_pages()` = `[]`).
- dHash caseiro (Pillow, ~15 linhas — sem scipy/imagehash).
- `RawEvent.venue_name` (campo novo) + resolução de venue no loop de `events()` do pipeline.
- Runner `python -m nightlife.ingest_flyers` com move-to-processed.
- `vision_flyer` como source_type (contribuição standalone 0 em eventos — corrobora via multi-fonte).

### Não-objetivos (YAGNI)
- Upload via endpoint da API (sem consumidor; a UI vem depois).
- OCR de fallback (o agente de visão já lê melhor que OCR em flyer estilizado).
- Monitoramento automático de Instagram (fase futura; este extractor é o pré-requisito dele).
- Backend Claude API / Claude Code headless (adapters futuros da mesma interface).

## 4. Contrato de extração (anti-alucinação — spec original §8)

O prompt exige que o modelo retorne **apenas JSON** neste schema:

```json
{
  "event_name": "string | null",
  "date_text": "string | null — o texto da data COMO ESTA NO FLYER, ex. 'SEX 13/06 23h'",
  "venue_name": "string | null",
  "organizer": "string | null",
  "lineup": ["strings — nomes como escritos"] ,
  "price_text": "string | null",
  "ticket_url": "string | null",
  "instagram_handle": "string | null",
  "quotes": {"<campo>": "trecho textual do flyer que sustenta o valor"},
  "confidence": {"<campo>": 0.0-1.0}
}
```

Regras do contrato:
- **`null` para ausente — nunca inventar.** Campo sem `quote` correspondente é tratado como suspeito (confidence do campo cortada pela metade no pós-processamento).
- **`date_text` é texto cru**: a conversão para datetime é do nosso `parse_ptbr_datetime` (determinístico, testado, timezone SP) — nunca do modelo.
- Validação com Pydantic (já é dependência via FastAPI); JSON inválido ou schema violado → **1 retry** com o erro anexado ao prompt; falhou de novo → imagem pulada com erro registrado no run.

## 5. Componentes

- `src/nightlife/extraction/flyer.py` — `FlyerExtraction` (modelo Pydantic do schema), `FlyerExtractor` (Protocol: `extract(image_path) -> FlyerExtraction | None`), `flyer_to_raw_event(extraction, image_hash, *, reference) -> RawEvent | None` (**pura**: aplica `parse_ptbr_datetime` no `date_text`, monta o RawEvent, descarta se `event_name` é null; `source_url = f"flyer:{image_hash}"`).
- `src/nightlife/extraction/imagehash.py` — `dhash(image_path) -> str` (Pillow: grayscale → 9x8 → gradiente horizontal → 64 bits hex). **Pura** dado o arquivo.
- `src/nightlife/ingestion/codex_extractor.py` — `CodexExtractor`: monta o prompt, invoca `codex exec` headless com a imagem anexada e saída JSON, valida/retry. Flags exatos do CLI calibrados na implementação (task de smoke), como fizemos com a API da Sympla; requisito: modo não-interativo, imagem como input, stdout capturável.
- `src/nightlife/ingestion/flyer_source.py` — `FlyerSource(directory, extractor, *, reference)`: varre `*.jpg|*.jpeg|*.png|*.webp`, calcula dHash, extrai, produz `RawEvent`s; expõe `processed_paths` para o runner mover. Dedupe intra-lote por dHash (duas cópias do mesmo flyer no inbox = 1 extração).
- `src/nightlife/ingest_flyers.py` — runner: `FlyerSource` → `run_ingestion(label="flyers")` → commit → move processados para `flyers/processed/` → imprime contagens e erros.

## 6. Mudanças no pipeline (pequenas)

- `RawEvent` ganha `venue_name: str | None = None` (além do `venue` embutido existente).
- Loop de `events()` do `run_ingestion`: se `rev.venue` existe → `upsert_venue` (comportamento atual, Sympla); senão, se `rev.venue_name` existe → `_resolve_venue` (matching contra o catálogo, threshold 0.82) para ancorar `venue_id` **sem criar venue** — flyer tem nome sem geo e com typo; criar poluiria o catálogo de 220 venues.
- `EVENT_SOURCE_CONTRIBUTION["vision_flyer"] = 0` (implícito — não entra no dict): evento só-de-flyer vale ~40 (futuro+venue quando ancora) e sobe com corroboração multi-fonte (+20). Honesto com a incerteza da fonte.

## 7. Idempotência e cota

- **Evidência**: `source_url = flyer:<dhash>` — re-ingerir o mesmo flyer (mesmo conteúdo de imagem) atualiza a evidência em vez de duplicar; o dedupe de eventos protege contra flyers *diferentes* do mesmo evento.
- **Cota do Codex**: (1) imagens processadas saem do inbox (move para `processed/`); (2) dedupe por dHash intra-lote; (3) a extração só roda para imagens no inbox — nunca re-varre `processed/`.

## 8. Testes

Offline e determinísticos (não gastam cota):
- `dhash`: mesma imagem → mesmo hash; imagem levemente redimensionada → mesmo hash; imagens diferentes → hashes diferentes (fixtures geradas com Pillow no próprio teste).
- `FlyerExtraction`/validação: JSON válido, inválido, campo sem quote → confidence cortada.
- `flyer_to_raw_event`: monta RawEvent com data via `parse_ptbr_datetime` (ex. "SEX 13/06 23h" com reference fixa); `event_name` null → descarta.
- `FlyerSource` com extractor **fake** (Protocol!): varre pasta temporária, dedupe intra-lote por dHash, `processed_paths` correto.
- Pipeline: `RawEvent` com `venue_name` (sem venue) → ancora em venue existente via matching; nome desconhecido → `venue_id` None e **nenhum venue criado**.
- **Smoke real (1 task, gasta ~2 execuções de Codex)**: 1–2 flyers reais no inbox → `ingest_flyers` → evento no banco com evidência `flyer:<hash>`; calibra os flags do `codex exec`. Pré-requisito: `codex` logado (já verificado: v0.135.0 instalado).

## 9. Dependências

- `pillow` → runtime (dHash + validação básica de imagem).
- Codex CLI: dependência **externa de máquina** (não do projeto) — o runner falha com mensagem clara se `codex` não estiver no PATH.

## 10. Definition of Done

- [ ] `dhash` + `FlyerExtraction` + `flyer_to_raw_event` puros e testados.
- [ ] `CodexExtractor` com validação + 1 retry; falha → pula e loga.
- [ ] `FlyerSource` + `RawEvent.venue_name` + resolução no pipeline (ancora sem criar).
- [ ] Runner `ingest_flyers` com move-to-processed.
- [ ] Suíte offline verde; smoke real com 1–2 flyers extraindo evento pro banco.
- [ ] README com a seção do inbox de flyers.
