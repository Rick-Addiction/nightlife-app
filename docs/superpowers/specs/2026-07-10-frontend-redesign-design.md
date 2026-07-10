# Nightlife App — Ciclo C: Frontend Redesign "Rave Brutalista" — Design (Spec)

- **Data:** 2026-07-10
- **Status:** Design aprovado (brainstorming com mockups no visual companion; direção, estrutura e filtros escolhidos pelo usuário) — pendente revisão final do spec
- **Contexto:** o frontend atual (Plan H) é funcional mas básico: split fixo 42/58 desktop-only, cards simples, dropdown de gênero, sem flyer, sem detalhe. O usuário pediu "melhorar MUITO o frontend". Uso declarado: **celular na rua + desktop pra planejar** → mobile-first com desktop adaptativo. Mockups aprovados em `.superpowers/brainstorm/1983-1783688092/content/` (visual-direction, layout-mobile, sintese-estrutura, filtros).

---

## 1. Objetivo

O app que você abre sexta 21h na rua e responde "pra onde eu vou" em segundos: feed do dia com o **flyer do Instagram** como estrela, mapa com gaveta, diretório de locais vivos — tudo na estética **Rave Brutalista**, rápido no celular e confortável no desktop.

## 2. Decisões travadas (do brainstorming visual)

1. **Estética: Rave Brutalista.** Preto puro, rosa-choque `#ff2e88`, verde-neon `#00ff85`, bordas duras 2px, blocos chapados, tipografia 900/uppercase com tracking apertado, pins losango. Cultura de flyer.
2. **Estrutura: 3 abas** (MAPA · FESTAS · LOCAIS) na barra inferior (mobile). **FESTAS = tela inicial**, no formato feed "Esta Noite" (manchete grande + card-herói com flyer + lista). **MAPA = tela cheia com gaveta arrastável** (a lista mora na gaveta; pins interativos). **LOCAIS = diretório** com busca e badges de vivacidade.
3. **Flyer do IG de ponta a ponta** — "muito importante" (usuário): imagem nos cards (hero grande, thumb nas linhas), no mini-card do pin e no detalhe. Fonte: `flyers/processed/{shortcode}.jpg` (já persistidos pelo Ciclo B; o evento carrega o permalink do IG → shortcode).
4. **Filtros híbridos:** chips rápidos inline (presets de QUANDO + ≡ FILTROS com contador) + **sheet avançado** (QUANDO com data, ONDE com bairros + ⌖ perto de mim, SOM multi, EXTRAS: com-ticket/com-flyer/IG-ativo, confiança) com botão-resultado vivo ("VER N FESTAS →"). **Igual nas abas FESTAS e MAPA**; o MAPA ganha ainda o controle de **CAMADAS** (◆ festas / ■ locais verificados / □ só com festa hoje).
5. **Detalhe da festa** (sheet ao tocar em card/pin): flyer grande, data/hora, venue + endereço + status de vivacidade, tags, botões **TICKET → / IG / MAPA**.
6. **Desktop (≥768px):** header com nav (FESTAS | LOCAIS) + layout fixo feed 40% / mapa 60%; mesma linguagem.
7. **Abordagem: rebuild-in-place** — mantém React/Vite/TS, react-map-gl/maplibre, Vitest, `api/client`, `data/join`, `map/geojson`; reescreve tema/estrutura/componentes. Sem dependência nova (gaveta com pointer events puros).
8. **Execução em DOIS planos** (spec único): **C-1 Fundação + Festas + Flyer** e **C-2 Filtros ricos + Mapa + Locais**. Cada plano com merge próprio e suítes verdes.

## 3. Arquitetura & arquivos

### Frontend (`web/src`)

```
theme.css            tokens brutalistas (--pink/--green/--black, bordas, tipografia)
App.tsx              estado de aba + fetch único (events+venues, como hoje) + breakpoint
tabs/FestasTab.tsx   feed "Esta Noite": manchete, hero c/ flyer, lista, chips rápidos
tabs/MapaTab.tsx     mapa cheio + Drawer + CAMADAS + mini-card de pin (C-2)
tabs/LocaisTab.tsx   diretório: busca nome/rua + badges de vivacidade (C-2)
components/BottomTabs.tsx   barra inferior mobile / nav de header desktop
components/EventCard.tsx    variantes hero (flyer grande) e linha (thumb 44px)
components/EventDetail.tsx  sheet: flyer grande + info + TICKET/IG/MAPA
components/VenueCard.tsx    local c/ ✓ verificado, IG HOJE, nº festas (C-2)
components/Drawer.tsx       gaveta 3 estados (fechada/meia/cheia), pointer events (C-2)
components/FilterChips.tsx  chips rápidos + botão ≡ FILTROS c/ contador
components/FilterSheet.tsx  sheet avançado c/ botão-resultado vivo (C-2)
filters/state.ts     reducer estendido: bairro, generos multi, nearMe, extras (C-2)
data/bairros.ts      bairros SP (centroides das sementes) + classify(lat,lng) (C-2)
```

O `MapView.tsx` atual (camada GL de venues + markers de evento) é a base do `MapaTab`; `EventList`/`FilterBar` atuais são substituídos.

### Backend (3 toques)

1. **Static de flyers:** `app.mount("/flyers", StaticFiles(directory=<FLYERS_DIR>/processed))` (diretório via config; criado se não existir).
2. **`EventOut.flyer_url: str | None`** — no `list_events`/`get_event`: dos `EventSource` do evento com `source_url` de permalink IG (`instagram.com/p/{shortcode}/`), extrai o shortcode; se existir arquivo `{shortcode}.(jpg|jpeg|png|webp)` em `flyers/processed/` (listagem do diretório cacheada por request), expõe `/flyers/{arquivo}`. Sem flyer → `null` (o card mostra variante texto).
3. **`VenueOut.ig_last_post_at`** — coluna já existe (Ciclo B); só expor no schema (alimenta badge "IG HOJE" e filtro IG-ativo).

### Dados & filtros

Fetch único como hoje (events com filtros de data/confiança na API + venues). Filtros novos são **client-side** sobre o array joinado: bairro (classify por lat/lng), ⌖ perto de mim (geolocation do navegador + raio), SOM multi-select, com-ticket (`ticket_url`), com-flyer (`flyer_url`), IG-ativo (`ig_last_post_at` recente do venue do evento). Presets de QUANDO continuam mapeando pra `date_from/date_to` na API (comportamento atual preservado).

## 4. Divisão em planos

### Plano C-1 — Fundação + Festas + Flyer
- `theme.css` novo (tokens) + reset visual.
- `App.tsx` com abas + breakpoint (mobile bottom tabs / desktop header + 40/60). Aba MAPA no C-1 = o `MapView` atual rebrandado (pins losango, cores novas) SEM gaveta/camadas ainda; aba LOCAIS = placeholder ("em breve") — o esqueleto navega desde o primeiro merge.
- `FestasTab` completo: manchete com contagem, hero + linhas, chips rápidos de presets (HOJE/AMANHÃ/FDS/TUDO) ligados ao reducer existente.
- Backend: static `/flyers` + `flyer_url` + testes.
- `EventDetail` sheet completo.
- **DoD C-1:** app usável no celular (3 abas, feed com flyers reais, detalhe), desktop 40/60, suítes verdes, smoke visual no navegador.

### Plano C-2 — Filtros ricos + Mapa + Locais
- `FilterSheet` (todas as seções; contador vivo) + `FilterChips` final; reducer estendido + `bairros.ts`.
- `MapaTab` completo: gaveta arrastável, CAMADAS, mini-card de pin com flyer, mesmos filtros.
- `LocaisTab` completo: busca, badges (✓ verificado = places_verified; IG HOJE/IG ativo = `ig_last_post_at`; nº de festas futuras), tocar → popup/detalhe do venue (o popup atual do mapa evolui).
- Backend: `VenueOut.ig_last_post_at` + teste.
- Manifest PWA mínimo (nome, ícone, standalone, theme-color preto).
- **DoD C-2:** filtros ricos nos dois contextos, mapa com gaveta/camadas, diretório vivo, PWA instalável, suítes verdes, smoke visual.

## 5. Não-objetivos (YAGNI)

- Favoritos/salvos, notificações, login — fora.
- Clusterização de pins; rotas/navegação até o local (o botão MAPA abre o Google Maps externo).
- Servir flyers de `flyers/` (inbox) ou `failed/` — só `processed/`.
- SSR/framework novo; biblioteca de UI/gestos (gaveta é nossa).
- Editar dados pela UI (fila de review continua fora).

## 6. Testes

- **Puros (Vitest):** reducer de filtros (cada dimensão nova: bairro, multi-gênero, nearMe, extras, contador de ativos); `bairros.classify` (dentro/fora/limite); helper de estados da gaveta (posições/limiares); derivação de contagem do botão "VER N FESTAS".
- **Componentes (Testing Library):** `FilterChips` (toggle preset, abrir sheet, contador), `FilterSheet` (marcar seções, aplicar, limpar), `EventCard` (variante hero com `flyer_url` vs texto sem), `EventDetail` (links corretos TICKET/IG/MAPA), `BottomTabs` (troca de aba), `VenueCard` (badges por sinal).
- **Backend (pytest):** `flyer_url` presente quando o arquivo existe (tmp dir com arquivo fake) e `null` quando não; extensões variadas; static mount responde 200; `ig_last_post_at` no payload.
- **Visual:** MapaTab/Drawer por smoke no navegador (padrão do projeto — canvas não tem teste unitário).
- Suítes atuais (268 py + 23 web) permanecem verdes em cada plano.

## 7. Riscos & mitigação

- **GPS**: permissão negada → "⌖ perto de mim" desabilita silenciosamente (chip apagado), demais filtros intactos.
- **Gaveta sem lib**: manter 3 estados discretos com transform/transition (sem física); lógica de snap em helper puro testado.
- **Flyer órfão** (imagem sem evento): nunca exposto — a URL só é emitida a partir de um evento com permalink válido. Path traversal impossível (StaticFiles + shortcode sanitizado no pipeline).
- **Regressão do mapa**: a camada GL/venues do Ciclo UI anterior é preservada (mudam cores/formas dos pins).
- **Suíte web existente**: `FilterBar`/`EventList` antigos saem → seus testes são SUBSTITUÍDOS pelos dos componentes novos (não deletados sem reposição).

## 8. Definition of Done (do ciclo)

- [ ] C-1 mergeado: 3 abas navegáveis mobile+desktop, feed com flyers reais, detalhe com ações, tema brutalista, suítes verdes, smoke visual aprovado pelo usuário.
- [ ] C-2 mergeado: sheet de filtros completo + chips nos dois contextos, gaveta + camadas no mapa, LOCAIS com vivacidade, PWA manifest, suítes verdes, smoke visual aprovado pelo usuário.
