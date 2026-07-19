# Nightlife App — Ciclo E-2b: Descoberta de Handle via Busca no IG — Design (Spec)

- **Data:** 2026-07-19
- **Status:** Design aprovado pelo usuário (brainstorm no chat; decisões A/A/A/A: começar pelos 32 com evento futuro / match forte auto + review / confirmação em 2 passos por perfil / runner sob demanda)
- **Contexto:** o E-2a leu os sites; sobra o buraco que o caso Oficina Club revelou — venue TEM Instagram, mas nosso rastreio (site/OSM/JSON-LD) não achou porque o "site" é Facebook. Banco: **1005 venues sem `instagram`** (734 nightclubs, 32 com evento futuro, 305 verificados no Google). A busca do IG resolve: procurar o nome do venue no Instagram e casar o perfil certo. O risco central é **envenenamento** (anexar handle errado alimentaria o detector E-3 e o intérprete E-1 com lixo — é o fantasma do Ciclo B, que já tem guardas: `canonical_handle`/`_NON_PROFILE`, `is_platform_handle`).
- **Fecha o Ciclo E-2** (E-2a sites + E-2b handles). Sinergia: handle descoberto aqui alimenta o E-3 de graça (o `follow_queue`/`scrape_queue` já pega venues com `instagram`).

## 1. Objetivo

Sob demanda, buscar no Instagram (pela burner) o nome dos venues sem IG — começando pelos 32 com evento futuro — e anexar `venue.instagram` SÓ com match forte confirmado por perfil; o resto vira candidato auditável. Zero envenenamento automático.

## 2. Decisões travadas (brainstorm)

1. **Escopo faseado**: os **32 com evento futuro** primeiro (prova a qualidade do matching antes de escalar); depois os 734 nightclubs. `--limit` controla.
2. **Match forte auto + resto review**: anexa sozinho só com evidência forte convergente; ambíguo/fraco → candidato auditável, NUNCA anexa no chute.
3. **Confirmação em 2 passos por perfil**: busca → pré-seleciona por nome → **busca o perfil** do melhor candidato → confirma por sinal forte (não só sinais fracos da busca).
4. **Runner sob demanda** (`discover_ig_handles --limit N`), fora do daily; controla volume na burner.

## 3. Peças

### 3.1 Probe (PRIMEIRA task — gate, como no feed do E-3)

Probe assistido: com a burner logada, buscar um nome (ex.: "Oficina Club") no IG e capturar TODAS as respostas JSON, achando a que serve os resultados de usuário. Objetivo: shape real de cada resultado — `username`, `full_name`, `is_verified`, `follower_count` (e o que mais vier). Fixture curada em `tests/fixtures/ig_search_sample.json`. **Gate:** busca serve JSON parseável → segue; senão → replaneja (ex.: DOM) ou aborta e reporta. O DOM/JSON do IG muda (lição do Ciclo B/E-3) — o parser puro sobre a fixture real é o contrato estável.

### 3.2 Busca + parser (`ingestion/ig_search.py`)

- `parse_search_results(graphql) -> list[SearchResult]` — PURO (fixture do probe): `SearchResult{username, full_name, is_verified, follower_count}`.
- `playwright_search(context, query) -> list[SearchResult]` — shell: navega/dispara a busca, captura o JSON, delega ao parser (espelha `playwright_fetch_posts`/`playwright_fetch_feed`).
- `fetch_profile_signals(context, handle) -> ProfileSignals` — shell: abre o perfil, extrai `bio_link` (link externo na bio), `category`, `bio_text`, `is_verified`, `follower_count` (reusa a captura de JSON do perfil).

### 3.3 Matching + decisão (`ingestion/handle_match.py`, PURO)

- `ProfileSignals{handle, bio_link, category, bio_text, is_verified, follower_count}`; `MatchDecision{action: "attach"|"review"|"reject", handle, reason}`.
- `shortlist(venue_name, results) -> list[SearchResult]` — por `name_similarity` (reusa `domain/matching.py`) acima de um piso; ordena por similaridade, depois seguidores.
- `decide(venue, best: SearchResult, signals: ProfileSignals) -> MatchDecision`:
  - **reject** se `canonical_handle` inválido / `is_platform_handle` (guardas do Ciclo B).
  - **attach** (forte) se nome bate forte E ≥1 confirmador FORTE:
    - **definitivo**: `bio_link` normalizado == `venue.website` normalizado (elo E-2a — mata o Oficina);
    - OU (`is_verified` E nome bate muito forte);
    - OU (categoria casa-noturna/bar E bio menciona SP/o bairro do venue).
  - **review** caso contrário (candidato plausível mas sem confirmador forte, OU vários candidatos empatados).
- Ambiguidade (2+ shortlist com similaridade próxima e sem desempate por confirmador) → **review**, nunca attach.

### 3.4 Runner (`discover_ig_handles.py`, sob demanda)

- Seleciona venues sem `instagram`, nightclub, futuros-primeiro (evento futuro → depois resto), `--limit`. Abre `open_context` da burner (headful).
- Por venue: `playwright_search(nome)` → `shortlist` → se vazio, nada → `fetch_profile_signals(best)` → `decide`:
  - `attach`: `venue.instagram = handle` + `VerificationLog(entity_type="venue", note="handle via ig_search: <reason>")`.
  - `review`: `VerificationLog`/`DedupeCandidate` com o candidato e o motivo; não anexa.
  - `reject`: nada (ou log leve).
- Blindado por venue (falha isolada não derruba). Delays humanos entre venues (busca + 1 fetch de perfil por venue). Commit por venue.
- Report: `{venue, action, handle, reason}` por venue; contagem attach/review/reject.

## 4. Não-objetivos (YAGNI)

- Os 1005 sem IG de uma vez — só os 32 futuros primeiro (`--limit`/faseado).
- Passo automático no daily — sob demanda; promover a semanal só depois de provado.
- Criar venue novo a partir da busca — só ANEXA handle a venue existente.
- Resolver Facebook/site como fonte — isso é o E-2a (feito).
- UI de auditoria dos candidatos review — `verification_logs`/`dedupe_candidates` via SQL por ora.
- Descoberta de organizer handle — só venue.

## 5. Testes

- **Puros (pytest):** `parse_search_results` (fixture real do probe: extrai os campos, ignora não-usuário); `shortlist` (piso de similaridade, ordem); `decide` (attach por bio_link==website; attach por verificado+nome forte; review por ambíguo; reject por platform/handle inválido; sem confirmador → review); normalização de URL (bio_link vs website).
- **Runner (pytest+DB):** `discover` com search/profile fakes injetáveis — attach seta `venue.instagram`+log; review não anexa mas loga; reject não faz nada; falha por venue isolada.
- **NUNCA IG real em teste.**
- **Smoke real (usuário/assistido):** probe primeiro; depois `discover_ig_handles --limit 5` começando pelos futuros (incluir o Oficina Club se estiver sem IG) → conferir attaches corretos e o que foi pra review.

## 6. Riscos & mitigação

- **Envenenamento** (o risco central): confirmação por PERFIL (não só busca) + só match forte anexa + resto review + guardas do Ciclo B (`canonical_handle`/`_NON_PROFILE`/`is_platform_handle`) + o confirmador definitivo bio_link==website. Falso-positivo é caro → a barra é alta de propósito.
- **Volume de busca na burner** (escrita? não — leitura, mais leve que follow): sob demanda + `--limit` + delays; ainda assim a busca repetida pode marcar → começar conservador.
- **Busca do IG brittle** (shape muda): probe valida antes; parser puro sobre JSON; se quebrar, o parser devolve vazio → nada é anexado (falha segura, não envenena).
- **Homônimo nacional verificado** (ex.: marca com o mesmo nome): o confirmador definitivo (bio_link==website) e o "bio menciona SP/bairro" separam a casa local do homônimo; sem isso → review, não attach.
