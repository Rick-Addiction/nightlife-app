# Nightlife App — Documento de Design (Spec)

- **Data:** 2026-06-28
- **Status:** Design aprovado — pendente revisão final do spec
- **Região-alvo:** São Paulo, Brasil
- **Modo:** Uso pessoal (single-user)

---

## 1. Objetivo

Construir o **grafo de dados da vida noturna de São Paulo**: um backend que descobre, verifica, armazena, deduplica e expõe **venues** (baladas, bares, casas de show, espaços de evento) e seus **eventos** — cada registro com evidência, rastreio de fonte, frescor (`freshness`) e score de confiança.

A tese central: o valor está na **camada de dados confiável**, não na UI. A interface inicial é deliberadamente mínima (lista + mapa); o esqueleto de dados é o produto.

---

## 2. Escopo

### No escopo (v1 — "esqueleto")
- Região única: São Paulo.
- Single-user. Sem auth, sem multi-tenant.
- **Foco: cultura de festa** — baladas, festas, eventos e festivais (não bares em geral). Ver §4.1.
- **Eixo duplo:** venues fixos (baladas, casas de festa) **e** festas/festivais itinerantes (ligados a organizer, sem venue fixo).
- Pipeline de 4 camadas (§4), construído como *walking skeleton* com dados mock primeiro (§11).
- Lista com filtro + mapa (tela mínima, depois).

### Não-objetivos (fora do v1 — YAGNI)
- Multi-cidade.
- Multi-usuário / autenticação / monetização.
- Grafo de artistas (`artists` / `event_artists`) — **adiado**; line-up fica como texto cru no evento.
- Endpoints de admin review formais — substituídos por aprovação 👍/👎 no Telegram.
- Instagram em escala / Graph API oficial — só quando/se virar produto (§5.3).
- UI elaborada.

---

## 3. Princípios

- **Nunca alegar 100% de cobertura.** O sistema é projetado para *medir* sua própria cobertura, frescor e verificação (§14).
- **Evidência sempre.** Todo venue e evento guarda de onde veio, quando, e o que foi extraído (§6.2).
- **Cru antes de normalizado.** Guardar o payload/campos extraídos originais antes de qualquer normalização.
- **Avareza de custo.** Reprocessar só o que mudou (via `raw_payload_hash`); cachear agressivo; priorizar fontes baratas.
- **Sem dados pessoais de participantes.** Só informação de venue / evento / negócio / conteúdo público.
- **Respeitar robots.txt, ToS e limites de API** nas fontes web/ticketing (postura sobre Instagram em §5.3).

---

## 4. Arquitetura — pipeline de 4 camadas

O usuário desenhou a ordem correta: **venue-first**. Catalogar os locais primeiro torna a descoberta de eventos *tratável* — em vez de varrer o "oceano" do Instagram, monitora-se apenas os canais dos venues já catalogados.

| Camada | O que faz | Como | Alimenta |
|---|---|---|---|
| **1. Catálogo** | descobre venues e produtoras | Google Places + OSM/Overpass + listas/agendas (ex: Resident Advisor) → venue (lat/long, categoria, status) + organizers | mapa |
| **2. Canais** | acha IG / site / ticketing / Telegram de cada venue | Places fornece o website → o site linka o `@` → `venue_sources` | liga venue ↔ fontes de evento |
| **3. Eventos** | extrai eventos dos venues monitorados | IG via Playwright (volume humano) + **canais de Telegram (API oficial)** + sites/ticketing via JSON-LD/HTML + share via Telegram → **vision extractor** é o cérebro comum | lista |
| **4. Saída** | consumo | API (FastAPI) → lista com filtro + mapa; Telegram bot (share-in + notificações) | usuário |

### 4.1 Foco de escopo: cultura de festa

O alvo é **baladas, festas, eventos e festivais** — não bares em geral. Isso encolhe o universo de ~10 mil+ lugares para algumas centenas de venues relevantes + as produtoras de festa, e mantém os dados densos em sinal.

**Categorias-alvo:**
- **Venues:** baladas/nightclubs, casas de festa, espaços/galpões que recebem festa ou festival. (Bar comum só entra se tiver programação de festa/balada.)
- **Eventos:** festas (em venue fixo ou itinerantes), eventos de nightlife, festivais.

**Eixo duplo (venue + organizer).** Boa parte da cena de festa em SP é de **produtoras itinerantes** — a mesma festa roda em locais diferentes. Logo, um evento pode existir ligado a um `organizer` **sem** venue fixo. O modelo já suporta isso (`events.venue_id` e `events.organizer_id` são nullable; o scoring premia fonte oficial de organizador). Organizers são cidadãos de primeira classe, não só venues.

**Monitoramento.** Como o universo já é focado, quase todo venue/produtora catalogado é relevante para monitorar. A flag `is_monitored` permanece — mas agora como **controle de atividade/qualidade** (desligar o que morreu ou parou de render), não como filtro para conter volume de bar.

---

## 5. Estratégia de fontes

### 5.1 Tipos de fonte (`source_type`)
`google_places` · `osm` · `official_website` · `ticketing` · `event_page` · `instagram` · `telegram` · `manual` · `vision_flyer`

Cada novo tipo de fonte implementa a mesma interface de ingestão (ver README — "como adicionar uma fonte"): recebe input bruto → devolve candidatos com `extracted_fields` + evidência → o resto do pipeline (normalização, scoring, dedup) é comum.

### 5.2 Separação conceitual central
- **"Entender o flyer"** (vision extractor) = núcleo de valor, limpo, genérico — serve a qualquer fonte de imagem.
- **"Obter o flyer"** (acesso ao IG) = parte sensível.

Construir o "entender" não depende de resolver o "obter".

### 5.3 Postura sobre Instagram (decisão de uso pessoal)

Decisão consciente para o v1 **pessoal**, distinta da postura comercial:

- Coleta via **Playwright na conta própria, baixo volume** (varre os perfis dos venues catalogados ~1×/dia, comportamento humano). É área-cinza de ToS; o risco (limitação/ban da própria conta) é aceito pelo usuário, pois o uso é pessoal e de baixo volume — não comercial.
- **Share-to-app (Telegram)** como complemento: pega *stories* e fontes externas (ex: amigo manda flyer no zap) sem nenhum atrito de ToS.
- **Caminho "limpo"** (sem scraping) fica documentado para quando/se virar produto: **Graph API com consentimento** (organizador conecta a conta via OAuth) + parcerias inbound. Não é necessário no v1.
- Mesmo no uso pessoal, mantém-se o princípio de **não coletar dados pessoais de participantes** — só o conteúdo de divulgação (flyer, evento, venue).

---

## 6. Modelo de dados

PostgreSQL + PostGIS. Coordenadas como `lat`/`lng` (PostGIS-ready) para queries geográficas (mapa, bbox).

### 6.1 Tabelas
- `venues` — nome, categoria, `lat`, `lng`, endereço, `status` (operational / closed / permanently_closed / unverified), `confidence`, `is_monitored`, `first_seen_at`, `last_seen_at`.
- `venue_sources` — evidência por fonte (§6.2), FK → venue.
- `events` — nome, `starts_at`, `ends_at`, `venue_id` (nullable), `organizer_id` (nullable), `status` (scheduled / cancelled / past), `lineup_text` (texto cru — grafo de artistas adiado), `genre`, `ticket_url`, `confidence`, `raw_fields` (cru antes de normalizar), `first_seen_at`, `last_seen_at`.
- `event_sources` — evidência por fonte (§6.2), FK → event.
- `organizers` — nome, canais (mantido leve; usado no scoring e dedup).
- `ingestion_runs` — `source`, `started_at`, `finished_at`, `status`, `records_found`, `records_created`, `records_updated`, `errors`.
- `dedupe_candidates` — par (a, b), `similarity_score`, `decision` (auto_merged / pending_review / rejected), tipo (event / venue).
- `verification_logs` — trilha de verificações/mudanças de confidence.

**Adiado (v2):** `artists`, `event_artists`.

### 6.2 Evidência (obrigatória em `venue_sources` e `event_sources`)
`source_url` · `source_type` · `fetched_at` · `raw_payload_hash` · `extracted_fields` (JSON) · `confidence_contribution` · `last_seen_at`

---

## 7. Confidence scoring

Módulo determinístico e testável (§13). Pontuações exatamente como no prompt original.

### Venue
- Listagem operacional no Google Places: **+30**
- Match no OSM: **+20**
- Site oficial encontrado: **+20**
- Link de Instagram/perfil encontrado: **+15**
- Evento futuro linkado ao venue: **+15**
- **Penaliza:** fechado / permanently_closed / registro antigo / não-verificado.

### Event
- Data futura encontrada: **+20**
- Venue casado: **+20**
- Fonte oficial do venue ou organizador: **+25**
- Fonte de plataforma de ticketing: **+25**
- Mesmo evento em 2+ fontes independentes: **+20**
- **Penaliza:** data ambígua, sem venue, data passada, status cancelado, fonte fraca.

### Decay temporal (freshness)
Confiança decai se o registro não é reconfirmado (nightlife é efêmero). Separar explicitamente "quantas fontes" de "quão fresco".

---

## 8. Extração de eventos

Ordem de tentativa, do mais estruturado ao menos:

1. **JSON-LD Schema.org `Event`** quando presente.
2. **Padrões HTML comuns** (seletores de agendas/sites de evento).
3. **Texto livre** via interface compatível com LLM, com **fallback determinístico** (regex/heurística) sempre disponível.
4. **Vision extractor** (flyers — fonte dominante no BR):
   - **pHash na entrada** — dedup de imagem (o mesmo flyer aparece em N lugares; processa uma vez só).
   - **Modelo multimodal com schema forçado** lê o *design* (fonte estilizada, texto sobre foto) + **OCR como cross-check e fallback determinístico**.
   - **Anti-alucinação:** retorna `null` para campo ausente (nunca inventa); devolve a *citação textual* do que leu como evidência; `confidence` por campo.

**Normalização PT-BR:** datas, dias da semana, horários, timezone (`America/Sao_Paulo`). Guardar `raw_fields` antes de normalizar.

> Nota de implementação: ao construir a parte de LLM/multimodal, consultar a skill `claude-api` antes de escolher modelo/SDK.

---

## 9. Deduplicação

- Normalizar nomes de **evento** e de **venue**.
- Comparar: similaridade de nome do evento, proximidade de data/hora, similaridade de venue/endereço, organizador, ticket URL.
- Criar `dedupe_candidates` com `similarity_score`.
- **Auto-merge** apenas duplicatas de alta confiança.
- Média confiança → **revisão** (no uso pessoal: 👍/👎 no Telegram).
- Atenção a **eventos recorrentes** (festa semanal/mensal) — não tratar ocorrências como duplicatas.

---

## 10. API (FastAPI)

- `GET /venues?city=&bbox=&type=&min_confidence=`
- `GET /events?city=&date_from=&date_to=&bbox=&genre=&min_confidence=`
- `GET /events/{id}`
- `GET /venues/{id}`
- Review/merge: no v1 pessoal, `POST /admin/review/venue`, `POST /admin/review/event` e `POST /admin/merge-events` viram **operações internas acionadas pelo Telegram** (👍/👎), não endpoints públicos formais.

---

## 11. Estratégia de construção — walking skeleton, mock-first

1. **Fio fino ponta-a-ponta com fixtures mock:** catálogo → canais → evento → API → tela boba, usando venues e flyers de mentira. Sem dependência de chave de API.
2. Quando o fio gira inteiro e os testes passam, **engrossar camada por camada** e trocar o mock pelas fontes reais (Places → OSM → ticketing → IG).
3. Isto é o `sample ingestion using mock data` do prompt original, e mantém o sistema testável desde o dia 1.

---

## 12. Stack

Postgres + PostGIS · FastAPI · workers Python (coletores Places/OSM, channel resolver, monitores de evento, vision extractor) · Playwright (IG) · httpx + parser HTML (JSON-LD/seletores) · modelo multimodal (vision) · OCR (fallback determinístico) · Telegram bot (share-in + notificações) · scheduler (cron, monitores ~1×/dia) · front MapLibre/Leaflet + lista (depois).

---

## 13. Testes (obrigatórios no v1)

- Parsing de datas em **português** (incl. abreviações/dias da semana/sem ano).
- **Deduplicação** de eventos.
- Cálculo de **confidence score** (venue e event).
- **Venue matching**.
- Parsing de **JSON-LD `Event`**.

---

## 14. Métricas (coverage / freshness / verificação)

O sistema mede a si mesmo (nunca alega 100%):
- **Coverage:** nº de venues catalogados; % monitorados; nº de eventos por semana.
- **Freshness:** idade da última verificação por venue/evento; distribuição de `last_seen_at`.
- **Verificação:** distribuição de `confidence`; % de eventos com 2+ fontes independentes.

---

## 15. Definition of Done (v1 — esqueleto)

- [ ] Pipeline roda ponta-a-ponta com fixtures mock.
- [ ] Banco populado com venues + events + evidência + scores.
- [ ] API serve `/venues` e `/events` com filtros e bbox.
- [ ] Os 5 testes (§13) passando.
- [ ] README: arquitetura + **como adicionar uma nova fonte**.

---

## 16. Roadmap futuro (pós-esqueleto)

Ordenado por **valor pessoal por esforço** (revisado em 2026-07-01 — o job-to-be-done é "que festa tá rolando essa semana?", que exige *eventos* + um jeito de *ver*, não catálogo completo):

1. **Refactor score-da-evidência + idempotência** (spec próprio) — pré-requisito das fontes reais.
2. **OSM/Overpass** (venues; spec próprio) — valida o caminho HTTP real e alimenta o mapa.
3. **Ticketing #1: Sympla ou Shotgun** (eventos reais de SP via JSON-LD) — a lista ganha vida. Extrair também `organizer`/`performer` do JSON-LD (campos hoje ignorados pelo parser).
4. **Digest mínimo no Telegram** (`python -m nightlife.digest`, "festas da semana") — fecha o loop de valor pessoal antes de qualquer tela.
5. Resident Advisor → **vision extractor de flyers** (pHash + multimodal + OCR) → IG pessoal (Playwright baixo volume) → share-to-app.
6. Telas ricas (lista + mapa MapLibre/Leaflet) · métricas de coverage/freshness expostas · grafo de artistas (busca por DJ).
7. **Google Places: adiado** — custa dinheiro e enriquece venue (que não é a dor); entra quando qualidade de catálogo virar gargalo sentido.
8. Eventual caminho de produto (Graph API consentida, multi-usuário, monetização).
