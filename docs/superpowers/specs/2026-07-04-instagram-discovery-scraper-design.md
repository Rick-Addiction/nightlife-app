# Nightlife App — Instagram: descoberta de handles + scraper de flyers — Design (Spec)

- **Data:** 2026-07-04
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** Próximo grande passo do roadmap (memória do projeto). O *moat* é entender flyers (Plano G, feito); esta é a metade "obter flyers": varrer o Instagram das produtoras/locais de SP e alimentar o inbox `flyers/` que o pipeline de visão já consome. Fecha o loop "obter ⊥ entender".

---

## 1. Objetivo

Descobrir automaticamente os perfis de Instagram dos locais/organizers que já conhecemos (a partir das fontes que já capturamos) e, com uma **conta burner** logada via Playwright, varrer esses perfis 1x/dia baixando as imagens dos posts recentes (+ legenda + metadados) para o inbox `flyers/`. O pipeline de extração de visão (Plano G) transforma cada flyer em evento no banco. Uso pessoal, single-user, ritmo conservador para não tomar ban.

**Não** é um scraper genérico de Instagram: o alvo é o conjunto fechado de handles descobertos a partir dos venues/organizers do nosso banco.

## 2. Decisões travadas (do brainstorming)

- **Acesso:** conta **burner** (descartável, não a principal) logada via Playwright persistent context — isola o risco de ban.
- **Descoberta de handle:** **automática**, das fontes já capturadas — tags OSM (`contact:instagram`/`website`), **sites** dos venues/organizers, e **páginas de detalhe da Sympla**. Nada de lista curada à mão.
- **Por post:** **imagem + legenda + metadados** (permalink, data do post). A legenda entra como dica de texto na extração; o permalink vira `source_url` da evidência.
- **Volume:** **conservador** — 1x/dia, headful, delays humanos aleatórios; 1ª varredura ~6 posts/perfil, depois só posts novos; caps baixos; números em config.
- **Mecânica de leitura do IG:** Playwright + **interceptar o JSON GraphQL/XHR** que o próprio IG carrega (menos frágil que seletores de DOM); DOM é fallback. Descoberta usa **httpx + extractors JSON-LD/freetext existentes** (páginas server-rendered), sem carregar browser à toa.
- **Escopo:** um plano só, mas internamente modular (descoberta ⟂ scraper ⟂ mudança na extração).

## 3. Arquitetura & fluxo

```
[Descoberta]  fontes já capturadas (tags OSM, sites, páginas Sympla)
      │  extraction/social.py (puro) + ingestion/handle_discovery.py
      ▼
  venue.instagram / organizer.instagram  (+ IgProfileState por handle)
      │
[Scraper]  Playwright (burner) → perfis dos handles descobertos
      │  ingestion/instagram_source.py  (parse puro isolado)
      ▼
  flyers/<shortcode>.<ext>  +  flyers/<shortcode>.json  (sidecar)
      │
[Extração — já existe, estendida p/ legenda]
      │  FlyerSource + extraction/flyer.py  → run_ingestion
      ▼
  Event no banco (evidência source_type="instagram", source_url=permalink)
```

Três metades independentes; cada uma entrega valor sozinha (descoberta já dá "venues com IG conhecido"; scraper enche o inbox; extração já existia).

## 4. Modelo de dados

- **`Venue`** — adicionar `instagram: str | None` e `website: str | None` (hoje não tem nenhum). Migration Alembic.
- **`Organizer`** — já tem `instagram`/`website`; passam a ser **populados** pela descoberta.
- **Nova tabela `IgProfileState`** — cursor de scraping por handle:
  - `handle: str` (único, canônico lowercase)
  - `last_shortcode: str | None` (último post visto — corta a varredura incremental)
  - `last_scraped_at: datetime | None`
  - `consecutive_failures: int` (auto-pausa handle morto/banido/privado após limiar)
- **Handles a varrer** = união distinta de `venue.instagram` e `organizer.instagram` não-nulos, cruzada com `IgProfileState`.
- **Evidência** — cada post vira evidência de Event via o sistema existente (`persistence/evidence.py`): `source_type="instagram"`, `source_url=permalink`. Handle descoberto é registrado (evidência/VerificationLog no venue/organizer).

## 5. Descoberta de handles

### 5.1 `extraction/social.py` (PURO — testável sem rede)
- `canonical_handle(raw: str) -> str | None`: normaliza `@Foo`, `instagram.com/foo/`, `https://www.instagram.com/foo?igshid=…` → `foo` (lowercase, sem barra/query). Rejeita caminhos não-perfil (`/p/`, `/reel/`, `/explore/`, `/stories/`) e handles inválidos.
- `handles_from_text(text: str) -> set[str]`: acha URLs de instagram e @menções num blob de texto/HTML.
- `handle_from_osm_tags(tags: dict) -> str | None`: `contact:instagram` → `instagram` → `website`/`contact:website` (se for URL de IG).
- `handle_from_jsonld(data: dict) -> str | None`: varre `sameAs` (lista/str) por URL de instagram.

### 5.2 `ingestion/handle_discovery.py` (orquestra; idempotente)
- Pula entidades que já têm `instagram` preenchido (cacheado — não re-fetch).
- **Venue:** lê as tags do `raw_payload` da `VenueSource` OSM → `handle_from_osm_tags`. Se nada e há `website` → fetch do site (httpx + `truststore`, timeout curto, best-effort) → `handle_from_jsonld`/`handles_from_text`.
- **Organizer:** fetch da página de detalhe do evento/organizer na Sympla (a partir do `source_url` das evidências) → JSON-LD `sameAs` / freetext → `organizer.instagram`.
- Falha de rede = log + segue (não fatal); delays educados entre fetches; grava handle + evidência.
- **Runner:** `python -m nightlife.discover_handles` (imprime quantos handles novos por tipo de fonte).

## 6. Scraper de Instagram (Playwright, burner)

### 6.1 Dependências
- `playwright` (Python) + `playwright install chromium`. Instalação sinalizada nos riscos (Windows + Avast podem interferir no download do browser).

### 6.2 Bootstrap de login (1x, manual)
- `python -m nightlife.ig_login` abre chromium **headful** com `user-data-dir` persistente (config). **O usuário loga a burner à mão** (resolve 2FA/challenge manualmente). A sessão persiste no diretório e é reusada nas varreduras seguintes. Nenhuma credencial é digitada por código (regra de segurança).

### 6.3 `ingestion/instagram_source.py`
- Carrega o persistent context (sessão da burner).
- Handles = `venue.instagram ∪ organizer.instagram` distintos, cruzados com `IgProfileState`. Ignora handles pausados (falhas ≥ limiar).
- Por handle (cap `max_profiles_per_run`):
  - Navega ao perfil; coleta shortcodes recentes rolando até bater no `last_shortcode` (incremental) ou no cap (`max_posts_first_sweep=6` na 1ª, `max_posts_incremental` depois).
  - **Intercepta as respostas GraphQL/XHR** dos posts → `shortcode`, URL da imagem, `caption`, `taken_at`. DOM como fallback.
  - Baixa a(s) imagem(ns) para `flyers/<shortcode>.<ext>` + sidecar `flyers/<shortcode>.json` = `{handle, permalink, caption, taken_at, venue_id?, organizer_id?}`.
  - Delays humanos aleatórios entre ações; headful.
  - Atualiza `IgProfileState` (`last_shortcode`, `last_scraped_at`). Challenge/erro repetido → incrementa `consecutive_failures`, back-off e pula.
- **Parse puro isolado:** `parse_profile_posts(graphql_json) -> list[IgPost]` (dataclass `IgPost` = shortcode/image_url/caption/taken_at). Testável offline com fixture; a navegação Playwright é só a casca de I/O — mesma disciplina do runner injetável dos flyers (Plano G).
- **Runner:** `python -m nightlife.ingest_ig` (headful, caps/delays conservadores de config; imprime perfis varridos / imagens baixadas / handles pausados).

## 7. Mudança na extração (legenda)

- **`FlyerSource.events()`** — para cada imagem, lê o sidecar `<name>.json` opcional; passa `caption`+`permalink`+`taken_at` para a extração e para o `RawEvent`. Imagem sem sidecar (drop manual) continua funcionando (caption/permalink = None).
- **`extraction/flyer.py`** — `FlyerExtractor.extract(path, *, caption=None)`: o prompt do Codex inclui a legenda como **dica de texto** ("a legenda do post diz: …"); a imagem continua a fonte primária; o contrato anti-alucinação (null p/ ausente, quotes como evidência, `adjusted_confidence`) fica intacto. `flyer_to_raw_event(..., permalink=None)` → `source_url = permalink` quando presente (evidência de IG real em vez de id sintético do flyer).

## 8. Config (`config.py`)

Novos knobs (todos com default conservador):
- Scraper: `IG_USER_DATA_DIR`, `IG_HEADFUL=True`, `IG_MAX_PROFILES_PER_RUN`, `IG_MAX_POSTS_FIRST_SWEEP=6`, `IG_MAX_POSTS_INCREMENTAL`, `IG_DELAY_MIN`/`IG_DELAY_MAX` (faixa de segundos), `IG_FAILURE_PAUSE_THRESHOLD`.
- Descoberta: `DISCOVERY_FETCH_TIMEOUT`, `DISCOVERY_SYMPLA_PAGES` (liga/desliga o fetch das páginas Sympla).

## 9. Testes

Fiel ao TDD do projeto:
- **Puros (o grosso):**
  - `social.py`: handles de URLs (com query/igshid), @menções, tags OSM (as 4 chaves), JSON-LD `sameAs`; rejeição de `/p/`, `/reel/`, `/explore/`; canonicalização (case, barra final).
  - `parse_profile_posts`: fixture GraphQL → lista de `IgPost` (com/sem caption; carrossel multi-imagem).
  - lógica do cursor incremental: para no `last_shortcode`; respeita caps.
  - `flyer_to_raw_event` com caption/permalink → `source_url=permalink`; sem sidecar → comportamento atual.
- **Descoberta (integração com I/O mockado):** httpx mockado com fixtures de HTML/JSON-LD → handle correto gravado no venue/organizer; idempotência (não re-fetch se já tem `instagram`); falha de fetch não derruba o run.
- **Fora (YAGNI / verificação manual):** navegação Playwright real contra a burner — **smoke manual** (login bootstrap + 1 perfil real → imagem+sidecar no inbox), não unit (Playwright não roda em CI aqui; mesma decisão do MapLibre no Plano H). A suíte pytest do backend segue verde.

## 10. Não-objetivos (YAGNI)

- Stories/reels em vídeo; scraping de comentários; múltiplas contas/rotação.
- Agendamento/cron (runner manual por ora; cron/Task Scheduler documentado como futuro).
- Resolver captcha/challenge automaticamente (login é sempre manual, headful).
- Backfill de histórico completo (só posts recentes; caps conservadores).
- Digitar credenciais por código (proibido — o usuário loga à mão no bootstrap).

## 11. Riscos & mitigações

1. **DOM/GraphQL do IG muda** → parsing frágil. Mitiga: parse isolado em função pura fácil de reparar + fallback DOM + fixtures que travam o formato conhecido.
2. **Ban da burner** mesmo conservador → auto-pausa por `consecutive_failures`, headful, delays humanos, caps baixos, 1x/dia.
3. **Install Playwright/Chromium no Windows + Avast** (mesma classe do TLS: `truststore` no Python, `--use-system-ca` no Node) → documentar o passo de install e possíveis flags de cert.
4. **Descoberta faz fetch de muitos sites** (lento/brittle) → best-effort, idempotente, cacheado (pula quem já tem handle), timeout curto, delays.
5. **ToS do Instagram** → uso pessoal single-user; o usuário aceita o risco; burner isola a conta principal.

## 12. Definition of Done

- [ ] `Venue.instagram`/`Venue.website` + `IgProfileState` migrados (Alembic).
- [ ] `extraction/social.py` puro + testado (URLs, @menções, tags OSM, JSON-LD, rejeições).
- [ ] `handle_discovery.py` popula `venue/organizer.instagram` das 3 veias (OSM, sites, Sympla), idempotente; runner `discover_handles`.
- [ ] `ig_login` faz bootstrap manual da sessão da burner.
- [ ] `instagram_source.py` varre handles, intercepta JSON, baixa imagem+sidecar, atualiza cursor, auto-pausa; `parse_profile_posts` testado com fixture; runner `ingest_ig` conservador.
- [ ] `FlyerSource`+`flyer.py` consomem sidecar (caption→dica, permalink→source_url); imagem pelada ainda funciona.
- [ ] Suíte pytest verde (puros + descoberta mockada); smoke manual do scraper documentado.
- [ ] README: como logar a burner + rodar `discover_handles` e `ingest_ig`.
