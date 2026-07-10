# Nightlife App — Ciclo D-1: Varredura de IG por Área — Design (Spec)

- **Data:** 2026-07-10
- **Status:** Design aprovado pelo usuário (brainstorm no chat; decisões A/A/A/A+tabela)
- **Contexto:** o smoke do C-2 revelou que a cobertura de eventos é operacional: a fila de IG (rotação antiguidade + quente/frio, cap 20/run) tinha varrido 14 de 178 handles; na Baixa Augusta, 2 de 68. O usuário quer **varrer uma área específica sob demanda e VER se o mapa atualiza** — com relatório por local pra autópsia. Descoberto junto: 22 de 23 eventos futuros extraídos de flyer ficaram **sem venue** (a ancoragem é só por nome escrito no flyer) → invisíveis no mapa. Sem consertar isso, o teste de área falha pelo motivo errado.
- **Decomposição acordada:** D-1 (este spec) → D-3 (identidade visual: logo do venue via foto de perfil do IG + og:image; imagem de evento pra fontes sem flyer) → D-2 (site como fonte de eventos: descoberta da página de agenda + extração). Cada um com spec/plano próprios.

## 1. Objetivo

Disparar a varredura de IG de uma região (bairro nomeado no CLI, ou círculo desenhado no mapa), encadear a extração dos flyers, ancorar os eventos no venue certo, e responder na UI: **"+N festas novas, +M locais ganharam pin"** — com uma tabela por local do que foi encontrado.

## 2. Decisões travadas (brainstorm)

1. **Área por bairro nomeado no CLI** (`--bairro augusta`, centroides das sementes + raio 2km default) **e por círculo escolhido no mapa** (modo alvo explícito).
2. **Cap: modo área varre TODOS os handles do círculo de uma vez** (Augusta ≈ 66; mais exposição da burner numa tacada — risco aceito pelo usuário; delays 4–11s preservados).
3. **UI: chip de progresso com poll + diff no final + refetch automático.** Um run por vez (lock). Fechar a aba não mata o run.
4. **Tabela "Relatório da varredura"**: linha por local — LOCAL | @HANDLE | STATUS | POSTS NOVOS | FLYERS | FESTAS CRIADAS (nome+data, ancorou?) — consultável durante (parcial) e depois do run.
5. **Gesto do círculo:** botão ⌖ VARRER ÁREA (junto do CAMADAS) entra em modo alvo; próximo toque define o centro; círculo com slider de raio 0.5–5km (default 2); botão vivo "VARRER N PERFIS →" com contagem client-side; toque fora cancela.

## 3. Peças

### 3.1 Ancoragem por handle (pré-requisito)

- O sidecar `{shortcode}.json` já carrega `handle`. `FlyerSource`/`flyer_to_raw_event` propagam o handle de origem no `RawEvent`.
- No pipeline: se a ancoragem por **nome** (comportamento atual, prioridade) não achou venue e o handle pertence a um **venue** (`venues.instagram == handle`), ancora nele. Handle de **organizer nunca ancora** (organizer dá festa em casa alheia).
- Trilha de evidência registra `anchored_by=ig_handle` (VerificationLog ou nota na evidência, seguindo o padrão existente).
- Efeito imediato: os 22 eventos futuros flutuantes de 2026-07-10 passam a ancorar nos próximos re-ingests (e todo run futuro aproveita).

### 3.2 Fila por área (`persistence/ig_state.py`)

- `handles_in_area(session, lat, lng, km) -> list[str]`: handles de venues com geo dentro do raio (haversine), ordenados nunca-varrido-primeiro depois mais-antigo. SEM cap (decisão 2). Organizers fora (sem geo).
- Reusa a infra existente (`ig_profile_states`, cursores, auto-pausa por falhas consecutivas).

### 3.3 Runner encadeado (`python -m nightlife.sweep_area`)

- Args: `--bairro <nome>` **ou** `--center <lat>,<lng> --km <r>` (forma que a API usa). Resolução do bairro: match por nome NORMALIZADO (lowercase, sem acento, substring) contra a tabela de bairros do backend (= `SEED_POINTS` do `places_source`, ex.: `--bairro augusta` casa "Augusta/Consolacao" e "Baixa Augusta/Consolacao" → usa o primeiro match; ambíguo demais (0 ou 2+ matches distintos além do prefixo comum) → erro listando os nomes válidos. Raio default 2.0, override `--km`.
- Fluxo: cria `AreaSweep` (status=running) → varre handle a handle (reusa `scrape_handle`; atualiza `report` por item) → extrai flyers baixados (reusa o fluxo do `ingest_flyers`) → casa eventos criados de volta aos itens do report (por shortcode do permalink) → computa diff (**eventos futuros novos** e **venues que ganharam o 1º evento futuro**) → status=done (ou error, com mensagem).
- Modelo novo `AreaSweep` (migration): `id, center_lat, center_lng, radius_km, label, status (running|done|error), started_at, finished_at, report JSONB, diff JSONB`.
- Item do report: `{venue_id, venue_name, handle, status (ok|falha|pausado), posts_novos, flyers: [shortcode], festas: [{event_id, name, starts_at, anchored}]}`.
- Blindagem: falha num handle não derruba o run (padrão do daily); lock = existe AreaSweep running → aborta com mensagem.

### 3.4 API local (sem auth — API escuta localhost, app pessoal single-user)

- `POST /admin/area-sweeps {lat, lng, km}` → 409 se já há run ativo; spawna `sweep_area` como **subprocesso destacado** (sobrevive ao reload da API/aba); retorna `{id}`.
- `GET /admin/area-sweeps/current` → o running, ou o último terminado: `{id, status, progresso: {fase: varrendo|extraindo, feito, total}, report, diff}`.

### 3.5 UI (MapaTab)

- **Modo alvo:** botão ⌖ VARRER ÁREA; toque no mapa define centro; círculo via camada GL (polígono gerado por helper puro `circleGeoJSON(lat, lng, km)`); slider de raio; contagem viva client-side (venues com `instagram` e geo dentro do círculo — helper puro `handlesInCircle(venues, center, km)`); confirmar → POST.
- **Chip de status** fixo (poll 5s no `/current` enquanto running): `⌖ VARRENDO 12/66` → `EXTRAINDO 8/48`; ao terminar: painel-diff **"+N FESTAS · +M LOCAIS COM PIN"** + refetch de events/venues.
- **Tabela:** sheet "RELATÓRIO DA VARREDURA" (abre pelo chip/painel), linha por local com os campos do item do report; festas com marcador de ancoragem (✓ venue / ⚠ sem venue).

## 4. Não-objetivos (YAGNI)

- Varredura por área de organizers (sem geo) — fora.
- Agendamento de varreduras por área — o daily continua com a rotação global.
- Múltiplos runs simultâneos, fila de runs — um por vez.
- Histórico navegável de sweeps na UI — só o atual/último (a tabela do banco guarda o resto).
- Autenticação nos endpoints /admin — localhost only.

## 5. Testes

- **Puros (pytest):** `handles_in_area` (dentro/fora/borda, ordem nunca-varrido-primeiro); ancoragem por handle (nome tem prioridade; organizer não ancora; sem match → segue sem venue); resolução `--bairro`→centro+raio; montagem do diff.
- **Integração (pytest):** runner com scraper/extractor fakes injetados (report vai sendo preenchido, diff correto, lock funciona); endpoints com TestClient (POST cria e 409 duplicado; GET devolve progresso/report).
- **Puros (Vitest):** `circleGeoJSON`, `handlesInCircle`; reducer/estado do modo alvo se houver.
- **Componentes (Testing Library):** chip de status (fases), painel-diff, tabela do relatório (fetch mockado).
- **Visual/real:** smoke do usuário varrendo a Baixa Augusta.

## 6. Riscos & mitigação

- **Exposição da burner** (run de ~66 perfis): risco aceito; delays 4–11s mantidos; auto-pausa por handle com 3 falhas consecutivas continua valendo; se o IG travar a sessão no meio, o run marca os restantes como falha e termina com diff parcial (não trava).
- **Quota do codex** (~50 flyers numa tacada): extração continua uma a uma com dedupe por dHash; falha de extração → failed/ (padrão atual).
- **Subprocesso destacado no Windows:** usar `creationflags=DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP` (ou `start_new_session`) pra sobreviver à API; PID salvo no AreaSweep pra diagnóstico.
- **Report JSONB crescendo durante o run:** updates por item com commit curto (a UI faz poll; consistência eventual é aceitável).
