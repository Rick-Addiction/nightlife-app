# Nightlife App — Relevância de venues (precisão da descoberta) — Design (Spec)

- **Data:** 2026-07-05
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** Follow-up da feature de IG. O set de venues (OSM) mistura vida noturna com buffets/festa-infantil (o `amenity=events_venue` do OSM inclui buffet), poluindo mapa, eventos e o scraper. Também há falsos-positivos de handle de IG (`sympla`, `ifood` — rodapé/badge de página). Esta camada decide o que é "vida noturna" e filtra o resto nas bordas.

---

## 1. Objetivo

Introduzir uma **classificação de relevância** de venues ("isto é vida noturna?") e aplicá-la nas bordas (descoberta, scraper, API) para que buffets/festa-infantil e handles de plataforma parem de poluir o app. Não-destrutivo: os dados ficam no banco, só inertes.

## 2. Números que motivam (2026-07-05)

220 venues: 77 `nightclub`, 114 `events_venue`, 29 sem categoria. ~38 têm nome de buffet/festa-infantil. Falsos-positivos de handle: `sympla`, `ifoodbrasil` (~2). 17 eventos foram criados de flyers de buffet (ruído).

## 3. Modelo de relevância (decisão-chave)

Módulo novo **PURO** `src/nightlife/domain/nightlife_relevance.py`. Estados:

```
venue_relevance(name, category, has_events, is_monitored) -> "blocked" | "relevant" | "dormant"
```

Regra (nesta ordem — **blocked tem precedência**):
1. **blocked** — `name` casa a blocklist de buffet/festa-infantil. Nunca é vida noturna, mesmo com evento (um buffet que postou flyer continua blocked).
2. **relevant** — `category == "nightclub"` OU `has_events` OU `is_monitored`.
3. **dormant** — o resto (`events_venue`/sem-categoria, sem evento). "Ainda não": promove-se sozinho a `relevant` quando ganhar um evento de festa real ou for monitorado.

`blocked` e `dormant` ficam fora do mapa/scraper/descoberta. A diferença é semântica (nunca vs ainda-não) e permite o comportamento híbrido pedido.

**Blocklist de buffet** (por palavra no nome, case/acento-insensível): `buffet`, `bufê`, `infantil`, `kids`, `salão de festa`, `salao de festa`, `aniversário`, `aniversario`, `festa infantil`. Aceita-se que vaza um pouco (precisão > recall aqui). Fácil de estender.

**Blocklist de handles de plataforma** (separada, para a descoberta): `sympla`, `ifood`, `ifoodbrasil`, `facebook`, `whatsapp`, `instagram`, `youtube`, `tiktok`, `linktr`, `linktree`. Handles assim nunca são o IG próprio de um venue/organizer — vêm do rodapé/badge da página.

Funções puras:
- `is_buffet_name(name) -> bool`
- `is_platform_handle(handle) -> bool`
- `venue_relevance(name, category, has_events, is_monitored) -> str`

## 4. Onde aplica (bordas; o core de scoring/dedupe não muda)

- **Descoberta** (`ingestion/handle_discovery.py`):
  - `discover_venue_handles`: pula venues cujo nome é buffet (`is_buffet_name`) — não gasta fetch de site em buffet.
  - Handle descoberto (venue OU organizer): se `is_platform_handle`, descarta (não grava).
- **Scraper** (`persistence/ig_state.py::handles_to_scrape`): só retorna handles de venues **relevant** (`nightclub` ou com evento ou monitorado) e de organizers (organizers não têm a poluição de buffet; ficam como estão, menos os platform-handles). Buffet/dormant não é varrido.
- **API** (`api/`): 
  - `GET /venues`: por padrão retorna só **relevant** (esconde `blocked`+`dormant`). Query param `include_all=true` reexpõe tudo (debug).
  - `GET /events`: esconde eventos cujo venue resolvido é **blocked** (tira o ruído de flyer de buffet). Eventos sem venue ou com venue relevant/dormant seguem aparecendo.

`has_events` de um venue = existe ≥1 `Event` com `venue_id` = ele. `is_monitored` = coluna `Venue.is_monitored`.

## 5. Limpeza dos dados já existentes (passo à parte, opt-in)

Um runner `python -m nightlife.cleanup_relevance` (ou trecho no runner de descoberta) que: (a) zera `instagram` de venues buffet e de handles de plataforma já gravados; (b) opcionalmente reporta/marca os ~17 eventos de flyer cujo venue é buffet. **Não deleta** venues; só limpa handles-lixo e reporta. A filtragem da API já esconde o resto sem precisar apagar.

## 6. Efeitos aceitos (confirmados)

- A blocklist de buffet é por palavra no nome → vaza alguns; aceitável.
- Esconder `dormant` do mapa **remove ~114 events_venue** até terem evento → o mapa fica bem mais nightclub-cêntrico e enxuto. Confirmado como desejado.
- A UI (Plano H) ganha o mapa limpo de graça (só consome a API já filtrada; sem mudança no `web/`).

## 7. Testes

- **Puro (o grosso):** `nightlife_relevance.py` — `is_buffet_name` (buffet/infantil/kids/salão, com e sem acento, case), `is_platform_handle` (sympla/ifood/... e um handle legítimo passando), `venue_relevance` nos casos: nightclub→relevant, buffet→blocked (mesmo com evento), events_venue sem evento→dormant, events_venue com evento→relevant, monitorado→relevant, sem-categoria sem evento→dormant.
- **Integração (poucos, alto valor):** `handles_to_scrape` só devolve handles de venue relevant; `discover_*` descarta platform-handle; `/venues` esconde blocked/dormant e `include_all` reexpõe; `/events` esconde evento de venue buffet. Fixtures no DB de teste.
- Suíte backend segue verde (137 + novos).

## 8. Não-objetivos (YAGNI)

- Classificador ML / por LLM (a heurística determinística basta).
- Deletar venues do banco (não-destrutivo; a API filtra).
- Reclassificar organizers por "vida noturna" (só o platform-handle filter se aplica a eles).
- Mudar a query do OSM (`events_venue` continua sendo ingerido; a relevância filtra na leitura).
- Curar manualmente o dormant→relevant (promoção é automática por evento).

## 9. Definition of Done

- [ ] `domain/nightlife_relevance.py` puro + testado (buffet, platform-handle, os 3 estados).
- [ ] Descoberta pula buffet e descarta platform-handle.
- [ ] `handles_to_scrape` só relevant.
- [ ] `/venues` filtra relevant (com `include_all`); `/events` esconde venue-buffet.
- [ ] Runner de limpeza dos handles-lixo já gravados (opt-in, não-destrutivo).
- [ ] Suíte verde; mapa da UI mais limpo (verificado consumindo a API).
