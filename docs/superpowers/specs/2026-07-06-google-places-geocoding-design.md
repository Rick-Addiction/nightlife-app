# Nightlife App — Geocoding via Google (Places/Geocoding) — Design (Spec)

- **Data:** 2026-07-06
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** O diretório do RA trouxe **607 venues sem geo** (606 com endereço em texto: rua, número, CEP, cidade). Sem lat/lng eles não viram pin no mapa e o dedup geoless ficou pela metade (ver [dedup geoless endurecido] — "sem geo → nunca auto_merge"). Esta feature geocoda esses endereços via Google **Geocoding API**, reativa a trava de distância do dedup e fecha o arco do dedup que ficou adiado.

---

## 1. Objetivo

Preencher `lat/lng` dos venues que têm `address` mas não têm geo, usando a Google Geocoding API (endereço em texto → coordenadas), com **cache** para nunca cobrar o mesmo endereço duas vezes. Depois de geocodar, rodar uma passada de **re-dedup** que finalmente funde os duplicados geoless que agora têm geo para confirmar (ex.: "Mundo Pensante" do RA vs. OSM).

## 2. Decisões travadas (do brainstorming)

1. **API = Geocoding API** (não Places Text Search/Find Place). Já temos o endereço; só falta virar coordenada. Mais barato (~US$5/1000 → ~US$3 pelos 606, uma vez) e mais robusto que casar por nome.
2. **Geocodar todos os sem-geo + filtrar por bbox de SP.** Preenche geo de todos (o dado é real e serve ao re-dedup); a função `is_in_metro_sp` fica pronta e o runner **reporta** o split dentro/fora. **Sem coluna nova nem hard-filter na API** agora — a API `/venues` e `/events` já filtra pelo `bbox` do viewport (YAGNI; ver §5).
3. **Backfill uma vez + passo diário, ambos com cache.** O runner roda agora (606) e entra no `daily.py`; venues novos do RA são poucos → custo contínuo ~zero. O cache (tabela) garante idempotência entre runs.
4. **Re-dedup nesta feature, após geocodar.** A passada re-avalia os recém-geocodados com `classify_venue_match` (agora COM distância → `auto_merge`/`review` válidos), funde o que a trava de <1km + nome confirmar, enfileira o resto.

## 3. Arquitetura & arquivos

Fluxo do runner `geocode_venues`: **(1)** seleciona venues `lat IS NULL AND address IS NOT NULL` → **(2)** para cada um: consulta o cache pelo endereço normalizado; se ausente, chama o `Geocoder` → grava no cache → preenche `lat/lng` (via `OK`) → **(3)** após geocodar todos, roda `rededup_geocoded` nos ids que ganharam geo.

**Arquivos novos:**
- `src/nightlife/domain/geo_scope.py` — `SP_METRO_BBOX` + `is_in_metro_sp(lat, lng)` (puro).
- `src/nightlife/ingestion/geocoder.py` — protocolo `Geocoder`, `GeocodeResult`, `GoogleGeocoder` (httpx).
- `src/nightlife/persistence/geocode_cache.py` — `normalize_address`, `cache_lookup`, `cache_store`.
- `src/nightlife/persistence/venue_merge.py` — `merge_venues`, `rededup_geocoded`.
- `src/nightlife/geocode_venues.py` — runner (backfill + re-dedup); entra nas `STEPS` do daily.
- `migrations/versions/xxxx_geocode_cache.py` — cria a tabela `geocode_cache` (down_revision = `a1b2c3d4e5f6`).

**Arquivos modificados:**
- `src/nightlife/models.py` — model `GeocodeCache`.
- `src/nightlife/config.py` — `GOOGLE_MAPS_API_KEY`.
- `src/nightlife/daily.py` — adiciona `geocode_venues` às `STEPS`.

## 4. Componentes

### 4A. `geo_scope.py` (puro)

```python
# bbox aproximado da Região Metropolitana de SP (min/max)
SP_METRO_BBOX = (-24.10, -23.30, -47.10, -46.30)  # (min_lat, max_lat, min_lng, max_lng)

def is_in_metro_sp(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    min_lat, max_lat, min_lng, max_lng = SP_METRO_BBOX
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng
```

### 4B. `geocoder.py`

```python
@dataclass(frozen=True)
class GeocodeResult:
    status: str                 # "OK" | "ZERO_RESULTS" | "ERROR"
    lat: float | None = None
    lng: float | None = None

class Geocoder(Protocol):
    def geocode(self, address: str) -> GeocodeResult: ...
```

`GoogleGeocoder(api_key)`: `GET https://maps.googleapis.com/maps/api/geocode/json` com `address`, `key`, `region=br`, `components=country:BR`. Lê o JSON:
- `status == "OK"` → `GeocodeResult("OK", lat, lng)` de `results[0].geometry.location`.
- `status == "ZERO_RESULTS"` → `GeocodeResult("ZERO_RESULTS")` (endereço não resolvido — cacheável).
- Qualquer outro (`OVER_QUERY_LIMIT`, `REQUEST_DENIED`, `INVALID_REQUEST`) ou exceção httpx → `GeocodeResult("ERROR")` (transitório — **não** cacheia).

### 4C. `geocode_cache.py`

```python
def normalize_address(address: str) -> str:
    return " ".join(address.split()).lower()   # trim + colapsa espaços + lowercase

def cache_lookup(session, address) -> GeocodeResult | None:   # None = não está no cache
def cache_store(session, address, result: GeocodeResult) -> None:  # grava OK e ZERO_RESULTS; ignora ERROR
```

Tabela `geocode_cache`: `address_norm` (PK, String), `status` (String), `lat` (Float, null), `lng` (Float, null), `created_at` (DateTime server_default now).

### 4D. `venue_merge.py`

`merge_venues(session, survivor: Venue, loser: Venue) -> Venue`:
- Move `VenueSource` do loser → survivor, **pulando** os pares `(source_type, source_url)` que o survivor já possui (esses são deletados junto com o loser); os demais recebem `venue_id = survivor.id`.
- Move os `Event` do loser: `Event.venue_id = survivor.id`.
- Preenche lacunas do survivor a partir do loser: `lat/lng` (só se survivor sem geo), `address`, `category`, `instagram`, `website`.
- `recompute_venue_confidence(survivor)`; `session.delete(loser)`.
- Remove `DedupeCandidate` cujo `a_id` ou `b_id == loser.id`.
- Retorna o survivor.

**Sobrevivente** (escolhido pelo chamador, `rededup_geocoded`): maior `confidence`; empate → menor `id` (mais antigo, tende a ser OSM sobre RA).

`rededup_geocoded(session, geocoded_ids: list[int]) -> dict`:
- Para cada `vid` em `geocoded_ids` (na ordem), se o venue ainda existe (não foi fundido) e tem geo:
  - `match_venue(cand_ref, [outros venues COM geo])` com `threshold=0.0`.
  - `classify_venue_match(best.score, distance_km=geo_distance_km(...))`.
  - `auto_merge` → escolhe survivor/loser pela regra acima, `merge_venues`; registra o vid perdido para pular depois.
  - `review` → cria `DedupeCandidate(kind="venue", decision="review", ...)` (se ainda não existe par igual).
- Retorna contagens `{merged, review, distinct}`.

### 4E. Runner `geocode_venues.py`

```python
def geocode_all(session, geocoder: Geocoder, *, reference) -> dict:
    # 1. backfill
    pend = session.scalars(select(Venue).where(Venue.lat.is_(None), Venue.address.isnot(None))).all()
    geocoded_ids = []
    for v in pend:
        res = cache_lookup(session, v.address)
        if res is None:
            res = geocoder.geocode(v.address)
            cache_store(session, v.address, res)
        if res.status == "OK":
            v.lat, v.lng = res.lat, res.lng
            geocoded_ids.append(v.id)
    # 2. re-dedup dos recém-geocodados
    dd = rededup_geocoded(session, geocoded_ids)
    # 3. relatório (in/out bbox SP)
    ...
    return {...}

def main():   # truststore.inject; lê GOOGLE_MAPS_API_KEY; erro claro se ausente; commit
```

## 5. Filtro de bbox — por que não hard-filter agora

A API já aceita `bbox` (viewport) e filtra `Venue.lat/lng` no SQL (`api/main.py`). O mapa passa o viewport, então venue fora de SP só aparece se o usuário arrastar o mapa até lá. Adicionar coluna `in_metro_sp` ou hard-filtrar por SP em toda query seria estado derivado redundante. `is_in_metro_sp` é entregue como função pura + usada no **relatório** do runner; o hard-filter (se um dia a #3 "pinar venues" precisar) é aditivo e trivial. **YAGNI.**

## 6. Chave da API & segurança

- `GOOGLE_MAPS_API_KEY` via variável de ambiente (lida em `config.py`). O usuário cria o projeto no Google Cloud, ativa **Geocoding API** + billing e gera a chave — Claude não insere credenciais. Sem a chave, `main()` aborta com mensagem clara ("defina GOOGLE_MAPS_API_KEY").
- A chave nunca é logada nem commitada. Só o `GoogleGeocoder` real a usa; testes injetam um fake.

## 7. Testes

- **`is_in_metro_sp` (puro):** ponto em SP capital → True; Itapema/SC → False; `None` → False.
- **`normalize_address`:** colapsa espaços/caixa; dois endereços equivalentes → mesma chave.
- **cache (DB):** `cache_lookup` miss → None; após `cache_store(OK)` → hit com coords; `cache_store(ZERO_RESULTS)` é cacheado (negative-cache); `cache_store(ERROR)` **não** grava. Segundo geocode do mesmo endereço não chama o geocoder (fake conta chamadas).
- **`merge_venues` (DB):** dois venues (survivor com geo, loser com evento + source distinta) → após merge: evento aponta pro survivor, VenueSource do loser movido, `(source_type, source_url)` duplicado não vira linha dupla, loser deletado, `DedupeCandidate` do loser some, lacunas preenchidas.
- **`rededup_geocoded` (DB):** venue A (OSM, geo) + venue B (RA, recém-geocodado <1km, nome quase igual) → `auto_merge` → 1 venue, evento/sources preservados. Par na faixa review → `DedupeCandidate`, 2 venues. Par >1km → distinct, nada muda. Não re-processa id já fundido.
- **runner `geocode_all` (DB, geocoder fake):** venues sem geo com endereço são preenchidos; `ZERO_RESULTS` fica sem geo; re-run não re-chama o geocoder (cache); relatório traz contagem in/out SP.
- Suíte backend verde. **Smoke real** (com a chave): backfill dos ~606, confirmar geo preenchida, split in/out SP reportado, "Mundo Pensante" (ou análogo) fundido, re-run idempotente (0 novas chamadas via cache).

## 8. Não-objetivos (YAGNI)

- Places Text Search / enriquecimento (site, telefone, rating) — só geo.
- Coluna `in_metro_sp` / hard-filter global por SP — o viewport já filtra o mapa.
- Interface de revisão dos `DedupeCandidate` — a fila já existe; consumi-la é outro tema.
- Re-geocodar venues que já têm geo (OSM/Sympla) — só preenchemos quem falta.
- Rate limiting sofisticado — 606 chamadas << 50 QPS da Google; cache elimina repetição.

## 9. Definition of Done

- [ ] `geo_scope.is_in_metro_sp` + bbox RMSP; testado.
- [ ] `geocoder.py`: `GoogleGeocoder` mapeia OK/ZERO_RESULTS/ERROR; protocolo `Geocoder` injetável; testado com fake.
- [ ] `geocode_cache`: tabela + `normalize_address`/`lookup`/`store`; negative-cache; ERROR não cacheia; testado.
- [ ] `venue_merge.merge_venues` + `rededup_geocoded`: merge move sources/events, escolhe survivor certo, não duplica evidência, limpa DedupeCandidate; testado.
- [ ] runner `geocode_venues` (backfill + re-dedup + relatório in/out SP); entra no `daily.py`; erro claro sem a chave.
- [ ] migration `geocode_cache` aplicada; `GOOGLE_MAPS_API_KEY` em config.
- [ ] Suíte verde; smoke real: 606 geocodados, split reportado, dup geoless fundido, re-run 0 chamadas.
