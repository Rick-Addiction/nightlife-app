# Nightlife App — Ciclo B: Instagram em escala — Design (Spec)

- **Data:** 2026-07-09
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** quase todo lugar tem Instagram, e é do IG que saem os eventos/updates (flyers → visão). Hoje só **14 venues** têm handle — mas o Ciclo A capturou **255+ sites oficiais** (`websiteUri` do Places), e há **275 venues com site e sem IG** (104 nightclubs) esperando extração. Dois gaps no código: (1) `discover_venue_handles` só busca sites vindos de **tags do OSM**, nunca o `venue.website`; (2) a varredura do IG não rotaciona — `handles_to_scrape` retorna ordem **alfabética** e o `ingest_ig` corta nos primeiros 8: com centenas de handles, só os 8 primeiros do alfabeto seriam varridos para sempre. Restrição física: **uma conta burner** (Playwright, sessão em `.ig_session`) — volume alto = risco de bloqueio.

---

## 1. Objetivo

Escalar a cobertura de IG de 14 pra centenas de venues (extraindo handles dos sites oficiais), varrer esses perfis de forma sustentável pra burner (rotação + prioridade + cap), e usar a atividade do IG como sinal fino de vida do venue.

## 2. Decisões travadas (do brainstorming)

1. **Ritmo: ~20 perfis/rodada** (`IG_MAX_PROFILES_PER_RUN` default 8→20, segue ajustável por env). Passada completa ~15 dias; delays humanos atuais mantidos.
2. **Fila em 2 níveis com cota:** nível 1 = venues **monitorados ou com evento futuro** (+ organizers com evento futuro); nível 2 = o resto. Dentro de cada nível, ordena por **antiguidade** (`last_scraped_at`; nunca-varrido primeiro). **Quentes levam até 70% do cap** (14 de 20); o resto completa com nível 2 — sem a cota, 50 quentes > 20 vagas e o nível 2 nunca rodaria.
3. **Sinal de vida do IG incluído neste ciclo:** `ig_last_post_at` no venue; `ig_stale` (>12 meses) **neutraliza só o `has_contact`** na relevância — não neutraliza `places_verified` (Google OPERATIONAL vence IG quieto) nem evento/monitorado. Sem dado → sem penalidade.
4. **Judgment calls aprovados:** limiar 12 meses; cota 70/30; `latest_post_at` só de handles de venue (organizer não tem relevância).

## 3. Arquitetura & arquivos

```
discover_handles (estendido)        ingest_ig (fila nova)               relevância
tag OSM → site OSM →            →   scrape_queue(cap=20): nível 1   →   ig_stale (>12m)
venue.website (NOVO; 275 sites      (quente, 70% do cap) + nível 2      neutraliza has_contact;
do Ciclo A) → handle_from_html      por antiguidade; scrape grava       places_verified/evento
                                    ig_last_post_at no venue            intactos
```

**Arquivos modificados:**
- `src/nightlife/ingestion/handle_discovery.py` — `discover_venue_handles` também busca `venue.website`.
- `src/nightlife/persistence/ig_state.py` — nova `scrape_queue(session, *, cap, pause_threshold)`.
- `src/nightlife/ingestion/instagram_source.py` — `scrape_handle` retorna `latest_post_at` (do `taken_at` do post mais recente visto no timeline, mesmo sem download).
- `src/nightlife/ingest_ig.py` — usa `scrape_queue`; grava `ig_last_post_at` no venue dono do handle.
- `src/nightlife/config.py` — `IG_MAX_PROFILES_PER_RUN` default 20.
- `src/nightlife/models.py` + migration — `Venue.ig_last_post_at` (DateTime tz, null; down_revision = `d4e5f6a7b8c9`).
- `src/nightlife/domain/nightlife_relevance.py` — kwarg `ig_stale: bool = False`.
- `src/nightlife/api/main.py` — computa `ig_stale` e passa.

## 4. Componentes

### 4A. Extração de handles (`handle_discovery.py`)

Em `discover_venue_handles`, a cadeia por venue sem IG vira: **(1)** tag OSM (`contact:instagram`) → **(2)** site da tag OSM → **(3) `venue.website`** (novo — cobre os 275 sites do Places). O fetch continua best-effort (exceção → log + segue), `handle_from_html` inalterado (JSON-LD `sameAs` → links instagram.com), buffets pulados, `is_platform_handle` filtra lixo, idempotente (pula quem já tem IG). O runner e o daily não mudam.

### 4B. Fila de varredura (`ig_state.scrape_queue`)

```python
def scrape_queue(session, *, cap: int, pause_threshold: int = 3) -> list[str]:
    # universo = handles_to_scrape (venues relevant com IG + organizers, menos pausados)
    # quente = handle de venue monitorado OU com evento futuro,
    #          ou de organizer com evento futuro
    # ordena cada nivel por IgProfileState.last_scraped_at ASC (None primeiro)
    # hot_slots = min(len(quentes), ceil(cap * 0.7)); frios completam ate cap
```
"Evento futuro" = `Event.starts_at >= hoje` (dia em America/Sao_Paulo, disciplina do projeto). `ingest_ig` troca `handles_to_scrape(...)[:cap]` por `scrape_queue(session, cap=config.IG_MAX_PROFILES_PER_RUN, ...)`.

### 4C. `latest_post_at` (`instagram_source.py` + `ingest_ig.py`)

O resultado de `scrape_handle` ganha `latest_post_at: datetime | None` = `taken_at` do post mais recente do timeline buscado (posts vêm recent-first; vale mesmo quando o incremental não baixa nada novo — o topo do timeline é visto em toda varredura). `ingest_ig`, após `record_success`, grava `venue.ig_last_post_at = result.latest_post_at` para o(s) venue(s) com `instagram == handle` (handle de organizer não toca venue). Falha do scrape → não toca.

### 4D. Relevância + API

`venue_relevance` ganha `ig_stale: bool = False`:

```python
alive = places_verified or source_count >= 2 or (has_contact and not ig_stale)
```
Tudo o mais intacto (blocked/eventos/monitorado). `api/main.py` computa `ig_stale = v.ig_last_post_at is not None and v.ig_last_post_at < now - 365d` e passa. `ig_state.handles_to_scrape` **não** passa `ig_stale` (um IG parado ainda deve ser varrido — é a varredura que detecta se voltou à vida).

## 5. Não-objetivos (YAGNI)

- Segunda conta burner / proxies / paralelismo de scraping.
- Sinal de atividade de organizer; relevância de organizer.
- Extração de eventos direto de captions (o caminho é flyer→visão, como hoje).
- Descoberta de handle por busca web (Google/Bing) — os sites oficiais cobrem; se sobrar venue relevante sem site nem handle, ciclo futuro.
- Interface da fila de review (pendente de outro ciclo).

## 6. Riscos & operação

- **Burner é o gargalo:** cap 20 com delays humanos (4–11s) mantém o perfil de risco moderado; ajustável por env sem deploy. Perfis com 3 falhas seguidas continuam pausados (mecânica existente).
- **Sessão pode ter expirado** (`.ig_session`, último login 2026-07-05): o smoke real de scraping valida com **cap 3**; se o login caiu, o usuário reloga com `python -m nightlife.ig_login` — não bloqueia o merge (fila é testada offline).
- **Custo:** zero API paga (sites via httpx; IG via burner).

## 7. Testes

- **Extração:** venue com `website` (sem tag OSM) → fetch e handle setado; com tag OSM → tag vence (não busca site); IG já preenchido → intocado (0 fetch); buffet → pulado; fetch falha → segue.
- **`scrape_queue` (DB):** monitorado/evento-futuro entra no nível 1; ordem por antiguidade dentro do nível (None primeiro); cota 70/30 com mais quentes que o cap; frios completam quando quentes < cota; pausados fora; cap respeitado; organizer com evento futuro é quente.
- **`latest_post_at`:** fake posts com `taken_at` → resultado carrega o mais recente; timeline vazio → None; incremental sem download novo ainda reporta o topo.
- **`ingest_ig` (unidade da função de gravação):** handle de venue grava `ig_last_post_at`; handle de organizer não toca venue.
- **Relevância:** `ig_stale` neutraliza `has_contact`; NÃO neutraliza `places_verified`/evento/monitorado; sem dado → sem penalidade.
- **API (DB):** venue nightclub só-contato com `ig_last_post_at` velho → some; com `places_verified` → fica.
- Suítes verdes. **Smoke real:** (1) `discover_handles` nos ~275 sites → contar handles novos; (2) `ingest_ig` com `IG_MAX_PROFILES_PER_RUN=3` → fila nova ordena certo, flyers baixam, `ig_last_post_at` gravado; se login expirou, reportar (não bloqueia).

## 8. Definition of Done

- [ ] `discover_venue_handles` busca `venue.website`; testado; idempotente.
- [ ] `scrape_queue` (2 níveis, cota 70/30, antiguidade, cap 20 default); `ingest_ig` usa; testado.
- [ ] `latest_post_at` no scrape + `Venue.ig_last_post_at` (migration) + gravação no ingest; testados.
- [ ] `ig_stale` na relevância + API; testado.
- [ ] Suítes verdes; smoke: handles novos contados; rodada cap-3 do IG validada (ou login expirado reportado).
