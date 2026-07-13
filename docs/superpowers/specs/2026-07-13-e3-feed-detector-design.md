# Nightlife App — Ciclo E-3: Detector via Feed "Seguindo" — Design (Spec)

- **Data:** 2026-07-13
- **Status:** Design aprovado pelo usuário (brainstorm no chat; decisões: follows automatizado lento / poll noturno 45min / cursor por-handle)
- **Conta usada:** o follow + feed rodam na **burner ANTIGA já aquecida** (a que o `ingest_ig` usa há meses — `.ig_session/`), NÃO na @radarsp.noite. Decisão do usuário: conta com histórico de leitura aguenta melhor a ação de escrita (follow) de 180 contas do que uma conta nova e fria. A @radarsp.noite fica de reserva (e pronta pro trilho oficial futuro).
- **Contexto:** o E-1 ensinou o sistema a INTERPRETAR posts (imagem+legenda → ações). Hoje a coleta é uma **varredura cega**: `ingest_ig`/`scrape_queue` visita ~20 perfis/dia por antiguidade, passada completa dos ~180 handles ≈ 9 dias — detecção de festa nova é lenta e o tráfego na burner é alto (1 request por perfil). O usuário perguntou por "recursos do IG que avisam post novo". Análise (2026-07-13): **webhook oficial inviável** para contas de terceiros; **sininho** cai na aba de notificações só no app (web é inconsistente); **Business Discovery oficial** exige App Review/Advanced Access (2-6 semanas, verificação de negócio, app Live, política de privacidade, screencast) → **abandonado por ora** (vira faixa futura; app Meta `1340060348294218` e a conta Business @radarsp.noite já criados ficam prontos se um dia submetermos). **O caminho sem gate é o feed "Seguindo"**: a burner seguindo os venues vê os posts novos de TODOS numa superfície só, ~99% menos requests que varrer perfil a perfil.

## 1. Objetivo

Trocar a varredura cega por um **detector**: a burner @radarsp.noite segue os venues, lê o feed "Seguindo" a cada 45 min (janela noturna), detecta "venue X postou o post Y", busca só aquele post e joga no intérprete do E-1. Detecção de festa nova em < 1h no horário que importa, com uma fração do tráfego. A varredura atual vira reconciliação semanal (fallback + o que o feed perdeu).

## 2. Decisões travadas (brainstorm)

1. **Follows automatizado lento**: a burner segue **15–20/dia** (config), delays humanos, **quentes primeiro** (venue com festa futura / monitorado / região do laboratório), **auto-pausa no 1º checkpoint** (reusa `consecutive_failures`). Ramp-up dos ~180 em ~10-12 dias. Venue novo com handle entra na fila.
2. **Poll do feed a cada 45 min, janela 10h–02h** (America/Sao_Paulo). Tarefa agendada SEPARADA do daily das 05:00. Silêncio de madrugada (comportamento humano; e a detecção de festa anunciada às 4h pode esperar as 10h).
3. **Cursor por-handle**: guarda o último shortcode visto por handle (reusa `IgProfileState.last_shortcode`), não um timestamp global — não perde posts em rajada.
4. **Trilho oficial (Business Discovery) FORA de escopo** — App Review é faixa futura, não bloqueia nada.
5. **Varredura atual (`ingest_ig`/`scrape_queue`) rebaixada a reconciliação semanal** — fallback se a burner cair + pega posts fora de ordem / contas ainda não seguidas.

## 3. Peças

### 3.1 Probe empírico (PRIMEIRA task — valida a premissa)

Antes de qualquer código de detector: script/sessão manual que, com a burner logada e ~5 venues já seguidos, abre o **feed "Seguindo" cronológico** E a **central de notificações do web**, e registra o que é **parseável de forma estável**: shortcode do post, @autor, timestamp, ordem cronológica. Saída = um relato "o feed web entrega X, as notificações entregam Y". **Gate de decisão:**
- Feed cronológico parseável → segue o design (detector = feed).
- Feed não confiável mas notificações sim → detector = notificações (mesmo resto do pipeline).
- Nenhum confiável → aborta o E-3, mantém a varredura como principal (e reporta ao usuário).

O DOM do IG web muda com frequência (lição do Ciclo B) — o probe é o que impede construir em cima de premissa falsa.

### 3.2 Fila de follows (`persistence/follow_queue.py` + runner `follow_venues.py`)

- `follow_queue(session, cap) -> list[str]`: handles de venues AINDA NÃO seguidos (coluna nova ou estado), quentes primeiro (mesmo critério de `_hot_handles` do `ig_state`), depois por antiguidade de descoberta. Cap = `IG_MAX_FOLLOWS_PER_RUN` (default 18).
- Estado "seguido": nova coluna em `IgProfileState` (`followed_at: datetime|None`) via migration, OU tabela dedicada — decidir no plano (reusar IgProfileState é mais simples).
- Runner `python -m nightlife.follow_venues` (headful ou headless conforme burner): abre contexto Playwright, pra cada handle vai ao perfil e clica "Seguir" com delays 4-11s; marca `followed_at`; auto-pausa global se detectar checkpoint/bloqueio (aborta o run, não força).
- Blindado por handle (falha isolada não derruba o run — padrão do daily).

### 3.3 Detector de feed (`ingestion/feed_watcher.py` + runner `watch_feed.py`)

- `parse_feed_items(html_or_dom) -> list[FeedItem{handle, shortcode, taken_at}]` — PURO, testável offline com fixture do DOM (o probe fornece o shape real).
- `new_since_cursor(items, cursor_by_handle) -> list[FeedItem]` — puro: filtra o que passou do `last_shortcode` de cada handle.
- Runner `python -m nightlife.watch_feed`: abre a sessão, lê o feed, extrai itens, cruza com o cursor (`IgProfileState.last_shortcode` por handle), e para cada item novo de venue-monitorável dispara o **fetch dirigido** (baixa imagem+legenda daquele shortcode reusando `playwright_download`/`playwright_fetch_posts` do `instagram_source`, grava no inbox `flyers/` com sidecar) → depois roda o `post_flow.process_inbox` sobre o inbox. Atualiza o cursor por handle.
- Só age em janela 10h-02h (o runner checa a hora SP e sai cedo fora dela — o agendador chama de hora em hora, o runner decide).

### 3.4 Rebaixamento da varredura + agendamento

- `daily.py`: `ingest_ig` sai do daily das 05:00 (ou vira semanal). Novo agendamento: `watch_feed` a cada 45min na janela; `follow_venues` 1x/dia; `ingest_ig` (reconciliação) 1x/semana. Ajustar `scripts/register_daily_task.ps1` (ou script novo) — **o usuário registra**.
- `discover_handles`/`ingest_flyers` (extração do inbox) continuam; o `watch_feed` alimenta o MESMO inbox, então `ingest_flyers` semanal também limpa resíduo.

### 3.5 Config novos

`IG_MAX_FOLLOWS_PER_RUN` (18), `FEED_WINDOW_START_HOUR` (10), `FEED_WINDOW_END_HOUR` (2), `FEED_POLL_ENABLED`. Sem dependência nova (tudo Playwright que já temos).

## 4. Não-objetivos (YAGNI)

- Business Discovery / API oficial — faixa futura (App Review).
- Sininho como fonte primária — só se o probe mostrar o feed inviável.
- Curtir/comentar/DM — a ÚNICA escrita nova é FOLLOW.
- Deixar de seguir (unfollow) — venue sai de relevância fica seguido, inócuo.
- Push/webhook, notificação no celular do usuário.

## 5. Testes

- **Puros (pytest):** `parse_feed_items` (fixture do DOM real do probe: extrai handle/shortcode/taken_at, ignora anúncios/sugestões), `new_since_cursor` (cursor por handle: primeiro-poll, sem-novos, rajada), `follow_queue` (não-seguidos, quentes primeiro, cap, exclui já-seguidos).
- **Integração (pytest):** runner de follow com Playwright fake (marca followed_at, auto-pausa em checkpoint simulado); `watch_feed` com fetcher/interpreter fakes (item novo → inbox → cursor atualizado; item já visto → no-op).
- **Sem chamar IG real em teste.**
- **Smoke real (usuário + assistido):** o probe (§3.1) primeiro; depois ramp-up de follows observado; depois um ciclo de `watch_feed` real detectando um post e virando evento.

## 6. Riscos & mitigação

- **Follow é a escrita mais vigiada do IG** → ramp-up lento (18/dia), delays humanos, auto-pausa no 1º checkpoint, burner já "aquecida" por meses de leitura. Se travar, a varredura semanal cobre.
- **Feed web instável (DOM muda)** → o probe valida ANTES; `parse_feed_items` isolado e testado com fixture; se quebrar em produção, cai no fallback da varredura (que continua rodando semanal). Detecção de mudança de shape = o parse devolve 0 itens → alerta no log.
- **Máquina desligada** → polls perdidos são recuperados: o cursor por-handle + a varredura semanal garantem que nada some, só atrasa.
- **Burner aquecida seguindo 180 baladas** → mais segura que uma conta fria, mas follow ainda é escrita: ramp-up de ~10 dias (18/dia), delays humanos, auto-pausa no 1º checkpoint. Começar conservador (ex.: 12/dia na 1ª semana) é ajustável. Se travar, a varredura semanal cobre.
- **Mistura follow + scrape na mesma burner** → a burner antiga já faz o scrape; adicionar follow concentra as duas ações nela (nenhum isolamento novo). Aceito: é a conta aquecida, e follow de venues é comportamento coerente com "conta que acompanha vida noturna". A @radarsp.noite continua reserva se a antiga cair.
