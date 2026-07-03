# Nightlife App — Fonte real #2: Sympla (eventos estruturados) — Design (Spec)

- **Data:** 2026-07-03
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** Segunda fonte real (a primeira, OSM, traz só venues). Sympla traz **eventos** — é o que faz a lista ganhar vida. Reconhecimento empírico feito em 2026-07-03 fundamenta as decisões abaixo.

---

## 1. Fatos empíricos (verificados)

- `robots.txt` da Sympla: `User-agent: * / Allow: /` — acesso permitido.
- A listagem web é casca de JavaScript (sem dados no HTML); o sitemap tem ~31k eventos do Brasil sem cidade na URL — ambos inviáveis para volume pessoal.
- **`POST https://www.sympla.com.br/api/v1/search`** (body `{"service": "/v4/search", "params": {...}}`) — a API JSON usada pelo próprio site — devolve eventos **estruturados**: `name`, `start_date_utc`/`end_date`/`timezone`, `location` (name, address, **lat/lon**, city, state, neighborhood), `organizer` (id, name), `url`, `theme_name`/`format_name`/`category_prim`, `is_free`, imagens. Suporta `limit`/`page` e `only` (projeção de campos).
- O parâmetro de filtro por cidade testado (`cityIn`) **não filtrou** de fato (veio evento do RJ) → filtro server-side é best-effort a calibrar; **filtro client-side por `city == "São Paulo"` é obrigatório e garantido**.
- Shotgun devolveu **429 na primeira requisição** (anti-bot agressivo) → **adiada** (exigiria backoff/retry cuidadoso).

## 2. Escopo

### No escopo
- `SymplaSource` + novo tipo `RawEvent` + método `events()` no protocolo `Source`.
- Escopo de conteúdo (decisão do usuário: opção **b**): o tema **"Festas e Shows" inteiro** (festas, baladas, shows, festivais — inclui shows em casas/teatros), somente **São Paulo (cidade)** e somente **eventos futuros**.
- Organizer como cidadão de primeira classe: `get_or_create_organizer` + `organizer_id` linkado no evento (liga a dimensão organizer do dedupe).
- Resolução do débito de timezone dia-limite (§6).
- Runner `python -m nightlife.ingest_sympla` + smoke real 2x (idempotência).

### Não-objetivos (YAGNI)
- Shotgun (429; fica para quando houver backoff), Resident Advisor.
- Fetch de páginas individuais de evento (a API já dá tudo; JSON-LD por página seria 1 req/evento à toa).
- Imagens, preços, lotes — ficam apenas no `raw_payload`.
- Digest Telegram (próxima fatia).

## 3. Mudança no protocolo `Source`

`ingestion/base.py` ganha:

```python
@dataclass
class RawEvent:
    name: str
    source_type: str                  # "ticketing"
    starts_at: datetime | None = None # tz-aware (UTC da API)
    ends_at: datetime | None = None
    venue: RawVenue | None = None     # venue EMBUTIDO (nome/endereco/lat/lon)
    organizer_name: str | None = None
    genre: str | None = None          # theme/format da API
    ticket_url: str | None = None
    source_url: str | None = None
    raw_payload: str = ""
```

E o protocolo `Source` ganha `def events(self) -> Iterable[RawEvent]: ...`. `MockSource` e `OSMSource` implementam `events() -> []` (mudança mínima).

## 4. Pipeline: terceiro loop

Em `run_ingestion`, após venues e pages, para cada `RawEvent`:
1. `venue = upsert_venue(...)` do `rev.venue` embutido (se houver) — evidência `source_type="ticketing"`, `source_url` = URL do evento. O catálogo cresce com geo de graça.
2. `organizer_id = get_or_create_organizer(session, rev.organizer_name).id` (se houver nome).
3. `upsert_event(EventInput(..., venue_id, organizer=rev.organizer_name, organizer_id=organizer_id, genre, ticket_url), SourceInfo("ticketing", ...), reference=...)`.

O fetch de `events()` entra no mesmo try/except de fonte-inteira (falha → run `status="error"`).

## 5. Persistência: organizer de primeira classe

- Novo helper `persistence/organizers.py`: `get_or_create_organizer(session, name) -> Organizer` (lookup por `normalize_name(name)` sobre os existentes — mesmo padrão O(n) do esqueleto; cria se não existe).
- `EventInput` ganha `organizer_id: int | None = None`; `events_repo` grava no create e preenche lacuna no merge (`event.organizer_id = event.organizer_id or candidate.organizer_id`).
- Com `organizer_id` linkado, `_key_from_row` passa a devolver o nome do organizer → a dimensão organizer do `dedupe_score` (+0.1) fica ativa; o cap de recorrência (corrigido em 2026-07-03) protege festas semanais do mesmo organizer.
- Scoring de venue: contribuição standalone de `"ticketing"` = **0** (o spec §7 de venue não tem esse sinal); o venue pontua via `future_event_linked` (+15) e corroboração multi-fonte futura (OSM/Places). O **evento** ganha `ticketing_source` (+25) normalmente.

## 6. Timezone: "dia" = America/Sao_Paulo (resolve débito conhecido)

A API da Sympla entrega datetimes em **UTC**. Sem correção, `starts.date()` (UTC) diverge do dia local em eventos entre 21h e meia-noite SP (UTC-3).

**Decisão:** o conceito de "dia" do sistema é o dia **em America/Sao_Paulo**.
- `confidence.py` (`future_date`/`past_date`) e qualquer comparação Python passam a usar `starts.astimezone(ZoneInfo("America/Sao_Paulo")).date()`.
- O pré-filtro SQL da API (`/events` default upcoming: `starts_at >= date_from` com cast UTC) mantém tolerância de ±3h na virada da meia-noite, **documentada e aceita** (efeito prático: a festa de ontem 23h ainda aparece de madrugada — desejável).
- Teste cobre o caso limite: evento sábado 23h SP (= domingo 02h UTC) conta como sábado.

## 7. A fonte (`ingestion/sympla_source.py`, espelha o padrão OSM)

- `parse_search_records(data: dict) -> list[RawEvent]` — **pura, offline**: mapeia registros da API → `RawEvent` (+ `RawVenue` embutido de `location` quando há nome; descarta registro sem `name`). `raw_payload = json.dumps(record, sort_keys=True)` (hash estável). Filtro client-side: `city == "São Paulo"` e tema "Festas e Shows" (campo `theme_name`; exato a confirmar na calibração — o registro real vai na fixture do teste).
- `SymplaSource(endpoint, page_limit=20, page_size=100)` — pagina o POST até esgotar/cap; params server-side best-effort (cidade/tema/data futura; calibrar na implementação); User-Agent identificado + timeout; o filtro client-side do parse é a garantia.
- Datas: `start_date_utc` → datetime tz-aware UTC (a conversão pra dia SP acontece na leitura, §6).

## 8. Runner + smoke

`src/nightlife/ingest_sympla.py` (com `truststore.inject_into_ssl()` — Avast): roda `run_ingestion(label="sympla")`, imprime run + contagens de venues/events/organizers + reviews. Smoke real **2x**: segunda execução não pode inflar contagens (evidência idempotente por `(evento, "ticketing", url)` + dedupe por ticket_url igual com datas compatíveis → auto-merge).

## 9. Testes

- `parse_search_records` offline com **fixture capturada da API real** (incl. um registro de outra cidade → filtrado; um sem name → descartado).
- `get_or_create_organizer` (cria/reusa por nome normalizado).
- Pipeline: `MockSource` com `events()` → venue embutido upserted + organizer linkado + evento com score correto; falha de fetch de `events()` → run error.
- Timezone: caso sábado-23h-SP em `confidence.py`.
- Dedupe: mesmo evento Sympla re-ingerido → merge (não duplica).
- Suíte permanece offline (fixture), determinística.

## 10. Definition of Done

- [ ] `RawEvent` + `Source.events()`; MockSource/OSMSource com `events() -> []`.
- [ ] Pipeline processa `events()` (venue embutido + organizer + evento) e trata falha de fetch.
- [ ] `organizer_id` linkado; dimensão organizer do dedupe ativa.
- [ ] "Dia" = America/Sao_Paulo em `confidence.py` (+ teste do caso limite).
- [ ] `parse_search_records` + `SymplaSource` + runner `ingest_sympla`.
- [ ] Smoke real 2x: eventos reais de festas/shows de SP no banco, sem inflação na re-execução.
- [ ] README menciona o runner. Suíte inteira verde.
