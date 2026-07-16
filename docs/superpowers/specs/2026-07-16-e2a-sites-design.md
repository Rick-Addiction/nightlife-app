# Nightlife App — Ciclo E-2a: Site como Fonte de Eventos — Design (Spec)

- **Data:** 2026-07-16
- **Status:** Design aprovado pelo usuário (brainstorm no chat; decisões A/A/A/A/A: extração híbrida / só sites próprios / fetch httpx→Playwright / crawl 1 nível / cadência semanal)
- **Contexto:** o E-1 ensinou o sistema a INTERPRETAR posts (imagem+legenda → ações); o E-3 detecta posts novos via feed. Falta a fonte que o laboratório-Augusta revelou: **o site da própria casa tem a agenda** (ex.: selva.club), e às vezes a festa está no site mas não no IG. Temos **289 venues com site** (186 site próprio, 80 IG-como-site, 12 linktree, 11 facebook). O E-1 já deixou o gancho: `Document.kind` prevê `"web_page"` "pelo mesmo contrato". Este ciclo é a metade "descobrir e extrair a página certa"; o intérprete/executor de ações são reusados.
- **Decomposição:** E-2a (este spec) = sites como fonte. **E-2b** (ciclo curto seguinte) = descoberta de handle via busca no IG (caso Oficina/site-Facebook, 111 venues sem IG).

## 1. Objetivo

Semanalmente, varrer os 186 venues com **site próprio**, achar a agenda, e transformar os eventos em ações ancoradas no venue — reusando o executor do E-1. JSON-LD determinístico quando existe (preciso, de graça); intérprete codex-sobre-texto quando não. Festa do site que coincide com IG/RA/Sympla na mesma noite **funde**; sem-data vira "DATA A CONFIRMAR".

## 2. Decisões travadas (brainstorm)

1. **Extração híbrida**: `parse_jsonld_events` (já existe) primeiro; se a página não tem `schema.org/Event`, **fallback pro intérprete do E-1 sobre o TEXTO da página** (codex sem `-i`, só prompt via stdin; contrato de ações idêntico).
2. **Escopo = só os 186 sites próprios**. IG-como-site (E-3 cobre), Facebook (login-walled + é E-2b), Linktree (agregador — fora por ora).
3. **Fetch híbrido**: httpx (+truststore, já temos) primeiro; se o HTML vier "vazio" (sem JSON-LD e sem texto de evento), **Playwright renderiza** (já temos).
4. **Crawl 1 nível**: home + seguir até ~3 links cujo texto/URL casa com agenda (`agenda/eventos/programação/shows/programacao`). Não é crawler.
5. **Cadência semanal, no daily**, com **cache por hash** de conteúdo (site parado → pula, não re-extrai).

## 3. Peças

### 3.1 Unificação: tudo vira AÇÃO ancorada no venue conhecido

Diferença-chave do IG: no site o **venue já é conhecido** (estou varrendo o site DELE) → ancora direto por `venue_id`, não por handle.
- **`Document`** (`ingestion/post_interpreter.py`) ganha `kind: Literal["ig_post", "web_page"]`, `image_path` vira opcional, e ganha `text: str | None` (texto da página) e `venue_id: int | None`.
- **`AddEvent`** (`extraction/post_actions.py`) ganha `starts_at_iso: str | None` — o JSON-LD já entrega data ISO parseada; `starts_at_iso` bypassa o `dates_ptbr` (que é pra texto PT-BR cru). `_do_add` usa `parse_iso(starts_at_iso)` se presente, senão `parse_ptbr_datetime(date_text)`.
- **JSON-LD → `add_event`**: cada `ExtractedEvent` vira `AddEvent(name, starts_at_iso=startDate, ticket_url, quotes={"name": name}, confidence={"name": 1.0})` (JSON-LD é estruturado = alta confiança, quote = o próprio nome).
- **codex-texto → ações**: o intérprete devolve `PostInterpretation` normal.
- **Executor** (`action_executor.execute_actions`) ganha um caminho de **ancoragem por venue_id** (quando `doc.venue_id` está setado, ancora direto; o fallback por handle continua pro IG). Cancel/update/dedup do E-1 valem igual → coincidência com IG/RA/Sympla funde.

### 3.2 Intérprete em modo texto (`codex_cli.py` + `post_interpreter.py`)

- `run_codex_text(prompt) -> str`: `codex exec --skip-git-repo-check -` com prompt via stdin, SEM `-i` (sem imagem). Mesmas lições de Windows (shell no win32, stdin). Codex roda text-only.
- `PostInterpreter.interpret` fica kind-aware: `web_page` → `run_codex_text` + prompt web (texto da página cercado, "você está lendo a AGENDA do site do local X"); `ig_post` → comportamento atual (imagem). Runner injetável nos dois modos (testes offline).
- `build_prompt` ganha variante web: troca "receber a IMAGEM de um post + LEGENDA" por "o TEXTO da página de agenda do site"; regras de ações idênticas (agenda→N add_event, sem-data→null, ignore etc.); mesma cerca anti-injeção no texto.

### 3.3 Fetcher (`ingestion/web_source.py`)

- `fetch_page(url) -> tuple[str, str]` (html, texto_visível): httpx GET (truststore, timeout, UA ASCII); se `_looks_empty(html)` (sem `<script type=application/ld+json>` E texto curto < N chars), re-fetch com Playwright renderizado (reusa `open_context`? não — página anônima; um `sync_playwright` leve). Falha → devolve o que tiver.
- `agenda_links(html, base_url) -> list[str]` — PURO: `<a>` cujo href/texto normalizado casa `AGENDA_WORDS`, resolvidos absolutos, mesmo domínio, dedup, cap 3.
- `_looks_empty(html) -> bool` — PURO: sem JSON-LD e sem sinal de evento (texto renderizável curto).

### 3.4 Fluxo (`ingestion/web_flow.py`)

- `crawl_venue(session, venue, *, fetcher, interpreter, reference) -> dict` (stats): busca home → se `web_last_hash` == hash(conteúdo), pula (`{"skipped": True}`) → senão, páginas = [home] + `agenda_links` (fetchadas) → por página: `parse_jsonld_events`; se vazio, `interpreter.interpret` sobre o texto → coleta ações → `sanitize_actions` → `execute_actions(doc com venue_id)` → atualiza `web_last_hash`/`web_checked_at`. Blindado por venue (falha isolada não derruba).
- Report por venue: `{venue, add, cancel, update, ignore, jsonld_vs_codex, skipped}`.

### 3.5 Persistência + runner + daily

- Colunas novas no `Venue`: `web_last_hash: str|None`, `web_checked_at: datetime|None` (migration).
- `crawl_sites.py`: itera venues com site próprio (website não-null, não instagram.com/facebook.com/linktr), roda `crawl_venue`, `IngestionRun(source="sites")`, commit por venue. Runner sob demanda + passo semanal.
- `daily.py`/agendamento: passo `crawl_sites` **semanal** (não diário) — no `register_feed_tasks.ps1` (ao lado da reconciliação semanal) ou um trigger próprio.

## 4. Não-objetivos (YAGNI)

- IG-como-site (E-3), Facebook (E-2b), Linktree (agregador) — fora.
- Descoberta de handle via IG — E-2b.
- Crawl multi-nível / sitemap / JS pesado além do render inicial.
- Servir a agenda do site na UI diferente (evento de site é evento normal, já aparece).
- Cache ETag/Last-Modified HTTP (hash de conteúdo é suficiente e robusto a servidores sem esses headers).

## 5. Testes

- **Puros (pytest):** `agenda_links` (casa palavras, mesmo domínio, cap, dedup); `_looks_empty` (com/sem JSON-LD); JSON-LD→AddEvent (starts_at_iso preenchido, ticket); `build_prompt` web (texto cercado, contexto do venue); `_do_add` com `starts_at_iso` (usa ISO, não ptbr).
- **Executor (pytest+DB):** ancoragem por `venue_id` (add ancora direto no venue do site); coincidência com evento IG/RA existente funde (não duplica).
- **Fluxo (pytest):** `crawl_venue` com fetcher/interpreter fakes — página com JSON-LD (usa determinístico, não chama codex); página sem (chama interpreter); cache-hit pula; falha por página isolada.
- **NUNCA rede/codex real em teste.**
- **Smoke real (usuário/assistido):** rodar `crawl_sites` num punhado (ex.: `--limit 5` começando pela selva.club) e conferir eventos ancorados; depois a célula da Augusta.

## 6. Riscos & mitigação

- **Sites são um zoológico** (JS, layouts variados): híbrido (JSON-LD→codex) + falha isolada por venue + cache; JSON-LD cobre os bem-comportados de graça.
- **Playwright em N sites é lento**: httpx primeiro (só renderiza quem precisa) + semanal + cache por hash.
- **Codex alucina em página longa**: JSON-LD primeiro; anti-alucinação por-ação/quote do E-1 vale igual; página muito longa → truncar o texto pro prompt (cap de chars).
- **Evento de site duplicando IG/RA**: o executor do E-1 já dedup/funde por nome+dia-SP; ancoragem por venue_id torna o match mais forte (mesmo venue garantido).
- **Fetch de site de terceiro**: respeita timeout, UA identificável, sem login/scraping agressivo — leitura de página pública de agenda (mesma postura das outras fontes).
