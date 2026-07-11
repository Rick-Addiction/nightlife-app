# Nightlife App — Ciclo E-1: Intérprete de Posts + Catálogo Denso — Design (Spec)

- **Data:** 2026-07-11
- **Status:** Design aprovado pelo usuário (brainstorm no chat; decisões A/A/A/A-revisada)
- **Contexto:** o laboratório-Augusta (área de teste escolhida pelo usuário, varrida 2x pela D-1) revelou onde festas REAIS se perdem: (1) o post-agenda da Selva (mês inteiro de festas) morre em `failed/` — contrato da visão é 1 flyer = 1 evento; (2) "NÃO SEJA CUZÃO" (Selva) entrou SEM data e ficou invisível (API default esconde `starts_at NULL`); (3) Supra Club Augusta (casa noturna 4,1★ no Maps) NUNCA entrou no catálogo — suspeita: saturação do teto de 20 do Nearby na célula densa (tipo está certo: "Casa noturna" = night_club); (4) ruído de evento (aula/curso/jogo/aniversário) e reposts duplicados (MUCHACHOS ×4) — não há filtro de relevância nem dedupe no nível de EVENTO. O usuário pediu **inteligência**: entender o post (imagem + legenda), decidir ações (adicionar 1, adicionar N, cancelar), e fundir IG + site do venue no mesmo funil de decisão (site = Ciclo E-2).
- **Ordem acordada do Ciclo E:** E-1 (este spec) → E-2 (site como fonte de documentos: descoberta da página de agenda + `web_page` no mesmo intérprete; descoberta de handle p/ casos site-Facebook como o Oficina Club) → D-3 (identidade visual) reordenado conforme apetite.

## 1. Objetivo

O post do IG deixa de ser "um flyer pra extrair" e vira "um documento pra INTERPRETAR": o modelo lê imagem + legenda inteira, com o contexto do venue (quem é, que festas dele já conhecemos, que dia é hoje), e devolve **ações editoriais** — adicionar 1..N eventos, cancelar, atualizar, ignorar com motivo. E o catálogo do laboratório fica completo: ferramenta de inclusão pontual por nome + re-varredura densa da célula.

## 2. Decisões travadas (brainstorm)

1. **Contrato multi-evento por AÇÕES** (não classificar-e-pular, não guarda-chuva): agenda do mês → N `add_event`; anti-alucinação POR AÇÃO (quote da legenda/imagem sustenta cada ação; sem quote → confiança ajustada cai → ação descartada).
2. **`cancel_event` autônomo só com prova forte**: quote explícita ("CANCELADA", "adiada para…") E match inequívoco (nome normalizado + data) com evento existente do MESMO venue → `status="cancelled"` + VerificationLog. Sem prova forte → candidato pendente em `verification_logs` (auditável), nada muda no evento.
3. **Evento sem data é VISÍVEL**: entra com `starts_at NULL`, API default passa a incluí-lo, UI mostra selo **DATA A CONFIRMAR** no fim da lista de FESTAS; sem pin de evento no mapa; venue conta como vivo no diretório. Quando um documento futuro trouxer a data → `update_event` promove.
4. **Catálogo**: `nightlife.add_place "<query>"` (Places Text Search, inclusão pontual com place_id/geo + enrich) **+ re-varredura DENSA da célula do laboratório** (raio inicial menor, subdivisão mais funda — ataca a perda por saturação dos 20 do Nearby). "Precisamos ter todos os dados" (usuário).
5. **Documento tipado, fonte-agnóstico**: `ig_post` (imagem + caption + handle) agora; `web_page` (texto/HTML) pluga no E-2 no MESMO intérprete e executor.

## 3. Peças

### 3.1 Contrato `PostInterpretation` (`extraction/post_actions.py`, novo)

Pydantic, união discriminada por `type`:

- `add_event`: `name`, `date_text` (cru PT-BR, pode ser null), `time_text?`, `lineup[]`, `genre?`, `ticket_url?`, `quotes{campo: trecho}`, `confidence{campo: 0..1}`.
- `cancel_event`: `event_name`, `event_date_text?`, `quote` (obrigatória), `confidence`.
- `update_event`: `event_name`, `event_date_text?`, `changes{date_text?/name?/ticket_url?}`, `quote`, `confidence`.
- `ignore`: `reason` ∈ {aula, aniversario, institucional, esporte, repost, sem_evento, outro}, `note?`.

`PostInterpretation { actions: list[Action] }`. Regra de saneamento (pura, testada): add/cancel/update sem quote que sustente o campo-chave → confiança ajustada < 0.5 → ação removida (mesmo espírito do `adjusted_confidence` atual). Post normal → lista com 1 `add_event`; agenda → N; repost de festa já conhecida → `ignore(repost)`.

### 3.2 Intérprete (`ingestion/post_interpreter.py`, novo — evolui o CodexExtractor)

- Backend: codex CLI (assinatura, custo marginal zero), 1 chamada por documento, imagem via `-i` + prompt via stdin (lições de Windows do Plano G preservadas: shell=True + shutil.which, imagem copiada pra nome controlado, stdin pra multi-linha).
- Prompt injeta CONTEXTO: nome + handle do venue dono do documento, data de hoje (America/Sao_Paulo), lista de eventos futuros já conhecidos do venue (nome + data ISO, cap 20). Instruções: entender o post; decidir ações; quotes obrigatórias; datas em texto cru PT-BR (o parse continua no `dates_ptbr`, determinístico); não inventar.
- Runner injetável (testes offline não gastam cota — padrão do projeto).
- Documento: dataclass `Document {kind: "ig_post", image_path, caption, handle, permalink}` — `web_page` entra no E-2 sem mudar contrato/executor.

### 3.3 Executor de ações (`persistence/action_executor.py`, novo)

- `add_event` → `RawEvent`/upsert existente (reuso do pipeline): ancoragem por handle (D-1) + nome do flyer; `starts_at` de `parse_ptbr_datetime(date_text)` ou NULL (visível como Data a Confirmar).
- `cancel_event` → matching forte contra eventos do venue: nome normalizado igual (mesma normalização da busca do LocaisTab) E (data igual OU evento é o único sem-data com esse nome). Match → `status="cancelled"` + `VerificationLog(note="cancelado via ig_post <permalink>")`. Sem match forte → `VerificationLog(note="cancel_candidate: ...")`, evento intacto.
- `update_event` → mesma matriz de match; aplica mudança + VerificationLog. Sem match → vira `add_event` (um "adiado para X" de festa que não temos é festa nova com data X).
- `ignore` → contabilizado (motivo) no relatório do run; nada persiste além do processed/.
- Eventos cancelados: somem do mapa/lista default (`status != 'cancelled'` no filtro da API), ficam no banco.

### 3.4 Fluxo de ingestão (substitui o caminho FlyerSource→flyer.py para IG)

- `sweep_area`/`ingest_flyers` passam a montar `Document`s do inbox (imagem + sidecar caption/handle/permalink) e chamar intérprete → saneamento → executor. dHash dedupe por conteúdo continua ANTES (imagem repetida nem chama o codex).
- Report da varredura (D-1) ganha por item: `acoes: {add: N, cancel: N, update: N, ignore: {motivo: N}}` — a tabela RELATÓRIO exibe.
- `FlyerExtraction`/`flyer.py` antigos: removidos após migração (testes substituídos — regra do projeto).

### 3.5 API/UI — sem-data visível

- `/events`: default passa a incluir `starts_at IS NULL` (junto do só-futuros) e a excluir `status='cancelled'`; ordenação: com data primeiro, sem-data no fim.
- FESTAS: eventos sem data no fim da lista com selo `DATA A CONFIRMAR` (tag ghost); EventDetail mostra "DATA A CONFIRMAR" no lugar da data.
- Mapa: evento sem data não vira pin de evento (sem dia); venue segue contando no diretório/camadas.

### 3.6 Catálogo (caso Supra + saturação)

- `python -m nightlife.add_place "<query>"`: Places **Text Search** (`places:searchText`, field mask id/nome/geo/endereço/tipos/status), lista os matches com índice, `--pick N` (ou único match → direto) cria o venue com evidência google_places (place_id como source_url, padrão atual) e roda o enrich Details nele. Loga os `types` retornados (confirma/refuta a hipótese da saturação pro Supra).
- `discover_places` ganha `--seed "<nome da semente>"` + `--radius <m>` + `--max-depth <n>`: re-varredura de UMA célula com raio inicial menor (ex.: 400m) e profundidade maior (ex.: 5), freio de 100m. Custo estimado ~US$1-2; sob demanda (fora do daily, como hoje).

## 4. Não-objetivos (YAGNI)

- Site como fonte (`web_page`) — E-2 (o contrato já nasce pronto pra ele).
- Descoberta de handle via busca no IG (caso Oficina/site-Facebook) — E-2.
- UI de auditoria dos cancel-candidates — `verification_logs` via SQL por ora.
- Batch de posts numa chamada só do codex (quotes por post ficariam frágeis).
- Re-varredura densa de TODAS as células — só a do laboratório; expansão é ciclo futuro.

## 5. Testes

- **Puros:** saneamento de ações (quote ausente derruba add/cancel/update; ignore passa); parser do output do codex (JSON válido/malformado/parcial); matriz de match do cancel/update (nome+data, único-sem-data, sem match); montagem do contexto (cap 20, só futuros do venue).
- **Executor (pytest+DB):** add com/sem data (NULL visível), cancel com prova forte (status+log), cancel sem match (candidato+intacto), update com match e sem match (vira add), ignore contabilizado.
- **API:** default inclui sem-data e exclui cancelled; ordenação.
- **UI (Vitest):** selo DATA A CONFIRMAR na lista e no detail; tabela RELATÓRIO com coluna de ações.
- **add_place/discover denso:** client Places fake (padrão do projeto); parse de matches; `--pick`.
- **Smoke real (usuário + assistido):** (1) `add_place "supra club augusta"`; (2) re-varredura densa da célula Baixa Augusta; (3) re-processar os failed/ da Selva pelo intérprete novo → festas do mês da Selva no app com data; (4) nova varredura por área pela UI e leitura do RELATÓRIO.

## 6. Riscos & mitigação

- **Alucinação em N eventos**: quotes por ação + confiança por campo + datas só via parser determinístico; agenda sem datas legíveis vira adds sem data (visíveis mas honestos) ou ignore.
- **Cancel falso-positivo**: prova forte obrigatória; resto é candidato auditável. Cancel perdido (post ambíguo) é aceito — auditável depois.
- **Prompt maior por post**: codex é assinatura; latência por post sobe um pouco (varreduras já são longas; ok).
- **Migração do caminho antigo**: testes de flyer.py substituídos pelos do intérprete (não deletados sem reposição — regra do projeto); `failed/` vira material de regressão real.
- **Text Search custo**: centavos por uso pontual; re-varredura densa ~US$1-2, sob demanda.
