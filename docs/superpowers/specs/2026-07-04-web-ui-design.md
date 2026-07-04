# Nightlife App — UI web (lista + mapa) — Design (Spec)

- **Data:** 2026-07-04
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** Fecha o pedido original ("visão em lista com filtro + visão de mapa"). O backend (A–G) serve dados reais via FastAPI (`/venues`, `/events`); esta é a camada que os torna *visíveis e usáveis*. Decisões de layout/estética validadas por mockups no companion visual.

---

## 1. Objetivo

Um app web que consome a API existente e mostra os eventos/venues de SP em **lista filtrável** e **mapa**, com uma barra de filtros única que dirige as duas visões. Uso pessoal, desktop primeiro.

## 2. Stack & integração

- **React + Vite + TypeScript**, em `web/` (novo diretório, isolado do backend Python).
- **Mapa:** MapLibre GL + `react-map-gl/maplibre`, tiles raster **CARTO dark** (`https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`) — grátis, sem chave.
- **Dev:** Vite em `localhost:5173`; proxy de `/api` → `http://localhost:8001` (FastAPI) no `vite.config.ts`. Zero CORS. Fluxo: sobe o uvicorn, `npm run dev`, abre o navegador.
- **Sem estado global externo** (Redux/Zustand): React state + `useReducer` para os filtros bastam no volume pessoal.

## 3. Layout & tema

- **Split (layout A)**: barra de filtros no topo (global) + toggle de visão **"Só lista" ↔ "Lista + Mapa"**.
  - Só lista: lista em largura total.
  - Lista + Mapa: lista à esquerda (~40%), mapa à direita. Clicar num card → destaca/centraliza o pin; clicar num pin → destaca o card na lista.
- **Tema Cyber duotone** (validado): fundo azul-noite (`#0a0e1e`→`#140a1e`), acento ciano (`#22e0e0`) + magenta (`#e055c0`), nome do evento em gradiente ciano→magenta, `effective_confidence` em destaque ciano. Tokens de tema num único `theme.css`/módulo.
- **Futuro (não neste plano):** layout B (mapa dominante + bottom sheet) para mobile.

## 4. Dados & o join no cliente (decisão-chave)

`GET /events` (`EventOut`) retorna `venue_id` mas **não** coordenadas. `GET /venues` (`VenueOut`) tem `lat`/`lng`. Portanto:

- O app busca **ambos** e faz o **join no cliente**: `venue_id` → `{lat, lng, name}` via um índice de venues.
- **Evento sem venue resolvível** (venue_id nulo, ou venue sem lat/lng) aparece na **lista, mas não no mapa** — honesto: sem geo não há pin. A lista marca esses ("local a confirmar").
- **Nenhuma mudança no backend.** A API fica intacta.

Tipos TS espelham os schemas Pydantic (`VenueOut`, `EventOut` — incluindo `effective_confidence`, `starts_at`, `genre`, `ticket_url`, `status`).

## 5. Filtros (dirigem lista e mapa juntos)

Barra única, refletida na querystring da API:
- **Período:** padrão "próximos" (a API já default-filtra futuro); presets rápidos (hoje / fim de semana / próximos 30 dias) mapeados para `date_from`/`date_to`. `include_past` opcional.
- **Gênero:** dropdown populado dos gêneros distintos presentes nos eventos carregados.
- **Confiança mínima:** slider → `min_confidence`.
- **Tipo de venue:** dropdown (`type=`) — afeta principalmente os venues no mapa.
- `bbox` a partir do viewport do mapa: **fase 2** (opcional; por ora carrega SP inteira e filtra no cliente).

Mudança de filtro → refetch de `/events` (e `/venues` quando `type` muda) → lista e pins atualizam juntos.

## 6. Componentes (arquivos focados)

```
web/
  index.html
  vite.config.ts            # proxy /api -> :8001
  package.json · tsconfig.json
  src/
    main.tsx · App.tsx       # shell, toggle de visão, tema
    api/client.ts           # fetch tipado + querystring dos filtros
    api/types.ts            # VenueOut, EventOut (espelham Pydantic)
    data/join.ts            # PURO: joinEventsWithVenues(events, venues) -> EventWithGeo[]
    filters/                # estado (useReducer) + <FilterBar/>
    list/EventList.tsx · EventCard.tsx
    map/MapView.tsx         # MapLibre, pins dos eventos mapeáveis, popup
    theme.css               # tokens do Cyber duotone
```

`data/join.ts` e a lógica de filtro/querystring são **puras** (sem React/DOM) — é onde mora a testabilidade.

## 7. Estados de UI

- **Loading:** skeleton nos cards + spinner no mapa.
- **Erro de fetch:** banner com "não consegui falar com a API — o uvicorn está no ar?" + botão retry.
- **Vazio:** "nenhum evento com esses filtros" com atalho pra afrouxar (ex. baixar confiança / incluir passado).
- **Evento sem geo:** aparece na lista com selo "local a confirmar"; não some.

## 8. Testes

Fiel ao TDD do projeto, pragmático pra frontend (**Vitest** + Testing Library):
- **Puros (o grosso):** `data/join.ts` (evento com/sem venue, venue sem geo → mapeável vs só-lista); construção da querystring a partir dos filtros (presets de data, genre, min_confidence, type); derivação da lista de gêneros.
- **Componentes (poucos, de alto valor):** `FilterBar` dispara a ação certa; `EventCard` renderiza campos e o selo sem-geo; estado vazio/erro aparece.
- **Fora (YAGNI):** E2E/mapa real — verificação visual (rodar e olhar). MapLibre não é testado unitariamente.

## 9. Não-objetivos (YAGNI)

- Layout mobile B (futuro).
- `bbox` por viewport (fase 2).
- Mudança no backend (join é no cliente).
- Auth, multi-usuário, escrita (a API é read-only).
- Servir o build pela FastAPI em "produção" (dev via Vite basta; documentado como opção futura).

## 10. Definition of Done

- [ ] `web/` scaffolded (Vite+React+TS), `npm run dev` sobe com proxy `/api`.
- [ ] Tipos espelham `VenueOut`/`EventOut`; `client.ts` busca com filtros.
- [ ] `join.ts` puro + testado; eventos sem geo caem só na lista.
- [ ] Barra de filtros dirige lista e mapa; toggle Só-lista ↔ Lista+Mapa.
- [ ] Mapa CARTO dark com pins dos eventos mapeáveis; card↔pin destacam-se.
- [ ] Tema Cyber duotone aplicado.
- [ ] Estados loading/erro/vazio/sem-geo.
- [ ] Suíte Vitest verde (puros + componentes-chave).
- [ ] README: como rodar a UI (uvicorn + npm run dev).
