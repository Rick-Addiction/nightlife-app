# Nightlife App — Descoberta de venues via Google Places Nearby — Design (Spec)

- **Data:** 2026-07-07
- **Status:** Design aprovado — pendente revisão final do spec
- **Contexto:** O geocoding preencheu a geo do que já tínhamos, mas revelou um gap de **cobertura de fontes**: baladas da Augusta como a **Selva** não estão em nenhuma fonte (nem OSM, nem diretório do RA, nem IG/flyer), e a **Supra** entrou pelo RA com endereço errado (Rua Humberto I em vez da Augusta). A ferramenta pra fechar isso é descoberta **geográfica**: dado um ponto, "quais casas noturnas existem ao redor?". Esta feature usa a **Places API (New) — Nearby Search** pra varrer os bairros de balada de SP e ingerir os venues descobertos pelo pipeline de sempre.

---

## 1. Objetivo

Descobrir venues de vida noturna por geografia (não por listagem prévia), usando a Places API (New) Nearby Search em pontos-semente curados dos bairros de balada de SP, e ingeri-los pelo `run_ingestion` existente. Como os resultados vêm **com geo + place_id**, o dedup funciona no melhor caso (auto_merge/review com distância; idempotência por place_id).

## 2. Decisões travadas (do brainstorming + probe real)

1. **Places API (New) — Nearby Search** (`places:searchNearby`). Já vem com lat/lng, nome canônico, place_id, endereço — sem geocodar depois.
2. **Híbrido: pontos-semente agora, grade sistemática depois.** ~12-14 centroides de bairros de balada; a grade fica como feature futura.
3. **Tipos (revisado pelo probe): `night_club` (núcleo) + `dance_hall`, `live_music_venue`, `concert_hall`, em chamadas SEPARADAS por tipo.** `event_venue` foi **descartado** — o probe mostrou que arrasta buffet/casamento/coworking/médico. Chamadas por tipo evitam que o teto de 20 deixe o ruído engolir as baladas.
4. **Runner sob demanda, fora do daily.** Venue novo é raro e cada chamada custa; dedup por place_id torna re-rodar idempotente.
5. **`rankPreference: DISTANCE`** (cobre a área uniformemente), raio ~1000m por semente.

### Achados do probe real (2026-07-07, ao redor da Augusta)

- `night_club` sozinho traz a Augusta noturna de verdade: **Supra Club Augusta**, Bofetada, Aloka, Hole, Lambi, Oficina, Bug, Casarão Augusta, Monica Club, Mangaba, Baile do Aquino…
- Uns poucos `bar`/`karaoke` vazam (têm `night_club` nos tipos secundários) — ruído baixo, tratado pela categoria.
- Até `night_club` sozinho **satura 20** na Augusta densa (há >20 no raio) → logar saturação como sinal pra grade futura.
- Resposta pode ter duplicatas internas (ex. "The Monica Club" 2×) — o dedup absorve.

## 3. Arquitetura & arquivos

Encaixa no protocolo `Source` existente (mesmo do OSM/RA/Sympla): `PlacesSource.venues()` faz as buscas e devolve `RawVenue`; `event_pages()`/`events()` retornam `[]`. Passa pelo `run_ingestion` → `upsert_venue` → dedup.

**Arquivos novos:**
- `src/nightlife/ingestion/places_client.py` — `PlacesClient` (httpx, **um `Client` reutilizado** — lição do geocoding, senão Errno 24), `PlaceResult`, `search_nearby(lat, lng, radius, included_type) -> list[PlaceResult]`.
- `src/nightlife/ingestion/places_source.py` — `PlacesSource` (Source), `SEED_POINTS`, `SEARCH_TYPES`, `_category_for(primary_type)`.
- `src/nightlife/discover_places.py` — runner sob demanda.
- Testes: `tests/test_places_client.py`, `tests/test_places_source.py`, `tests/test_discover_places.py`.

**Sem migration** — reusa `Venue`/`VenueSource`, `source_type="google_places"` (já em `VENUE_SOURCE_CONTRIBUTION`=30), `config.GOOGLE_MAPS_API_KEY`. **Pré-requisito:** habilitar a **Places API (New)** no projeto do Google Cloud (a Geocoding não cobre).

## 4. Componentes

### 4A. `places_client.py`

```python
@dataclass(frozen=True)
class PlaceResult:
    place_id: str
    name: str
    lat: float
    lng: float
    address: str | None
    primary_type: str | None

_ENDPOINT = "https://places.googleapis.com/v1/places:searchNearby"
_FIELD_MASK = "places.id,places.displayName,places.location,places.formattedAddress,places.primaryType"

class PlacesClient:
    def __init__(self, api_key, client=None):
        self._key = api_key
        self._client = client or httpx.Client(timeout=20.0)

    def search_nearby(self, lat, lng, radius, included_type) -> list[PlaceResult]:
        body = {"includedTypes": [included_type], "maxResultCount": 20,
                "rankPreference": "DISTANCE",
                "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lng},
                                                   "radius": float(radius)}}}
        headers = {"Content-Type": "application/json", "X-Goog-Api-Key": self._key,
                   "X-Goog-FieldMask": _FIELD_MASK}
        try:
            resp = self._client.post(_ENDPOINT, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []
        out = []
        for p in data.get("places", []):
            loc = p.get("location") or {}
            pid = p.get("id"); lat_ = loc.get("latitude"); lng_ = loc.get("longitude")
            if not pid or lat_ is None or lng_ is None:
                continue  # sem identidade ou sem geo: descarta defensivamente
            out.append(PlaceResult(
                place_id=pid, name=(p.get("displayName") or {}).get("text", ""),
                lat=lat_, lng=lng_, address=p.get("formattedAddress"),
                primary_type=p.get("primaryType")))
        return out
```
Erro (rede/quota/HTTP/JSON) → `[]` (o runner segue com o que conseguiu; nada aborta).

### 4B. `places_source.py`

```python
SEARCH_TYPES = ("night_club", "dance_hall", "live_music_venue", "concert_hall")

# centroides aproximados de bairros de balada de SP (precisao coberta pelo raio)
SEED_POINTS = [
    ("Augusta/Consolacao", -23.5545, -46.6620),
    ("Vila Madalena",      -23.5560, -46.6900),
    ("Barra Funda",        -23.5260, -46.6640),
    ("Lapa",               -23.5230, -46.7050),
    ("Itaim/Vila Olimpia", -23.5850, -46.6790),
    ("Pinheiros",          -23.5670, -46.6950),
    ("Centro/Republica",   -23.5440, -46.6420),
    ("Bela Vista/Bexiga",  -23.5580, -46.6450),
    ("Vila Mariana",       -23.5890, -46.6340),
    ("Moema",              -23.6000, -46.6650),
    ("Santana",            -23.5030, -46.6250),
    ("Tatuape",            -23.5400, -46.5760),
    ("Brooklin/Berrini",   -23.6100, -46.6900),
    ("Perdizes/Pompeia",   -23.5320, -46.6820),
]
_SEARCH_RADIUS_M = 1000

_NIGHTCLUB_TYPES = {"night_club", "dance_hall", "live_music_venue", "concert_hall"}

def _category_for(primary_type: str | None) -> str:
    return "nightclub" if primary_type in _NIGHTCLUB_TYPES else "bar"

class PlacesSource:
    def __init__(self, client: PlacesClient, *, seeds=SEED_POINTS,
                 types=SEARCH_TYPES, radius=_SEARCH_RADIUS_M, log=print):
        ...
    def venues(self) -> Iterable[RawVenue]:
        for _name, lat, lng in self._seeds:
            for t in self._types:
                results = self._client.search_nearby(lat, lng, self._radius, t)
                if len(results) >= 20:
                    self._log(f"[places] saturou 20 em {_name!r}/{t} (grade futura)")
                for r in results:
                    yield RawVenue(name=r.name, source_type="google_places",
                                   source_url=r.place_id, lat=r.lat, lng=r.lng,
                                   address=r.address, category=_category_for(r.primary_type))
    def event_pages(self): return []
    def events(self): return []
```

### 4C. `discover_places.py` (runner)

`main()`: exige `GOOGLE_MAPS_API_KEY` (aborta claro sem ela); `truststore.inject_into_ssl()`; `run_ingestion(session, PlacesSource(PlacesClient(key)), reference=hoje, label="places")`; commita; imprime `found`/`created` + total de venues.

## 5. Dedup — por que isto encaixa bem

Places entrega **geo + place_id**, então o `upsert_venue` opera no melhor caso:
- **Idempotência:** re-run casa por `(source_type="google_places", source_url=place_id)` → mesmo venue, nunca duplica.
- **Merge com o que já existe:** "Aloka Club" do Places perto do "Club Aloka" (RA) → `match_venue` + `classify_venue_match` **com distância** → `auto_merge` (enriquece com geo autoritativa) ou `review`.
- **Novos:** "Supra Club Augusta" (não existia) → criado, `category="nightclub"` → relevante.
- Duplicatas internas de uma resposta são absorvidas pelo mesmo mecanismo.

## 6. Não-objetivos (YAGNI)

- **Grade sistemática** sobre a Grande SP (fica pra depois; sementes cobrem os bairros de balada).
- **`event_venue`** e tipos de bar (bar/pub/wine_bar) — ruído; descartados.
- **Detalhes ricos** do Places (rating, reviews, telefone, horário) — só id/nome/geo/endereço/tipo (mantém o field mask no tier Pro).
- **Entrar no daily** — sob demanda; venues mudam devagar.
- **Cache de Places** (diferente do geocoding) — resultados podem mudar; e é sob demanda, não diário.

## 7. Custo & segurança

- ~14 sementes × 4 tipos ≈ **56 chamadas ≈ US$1.80** por run (Nearby Search Pro SKU; field mask sem rating/reviews). Sob demanda.
- `GOOGLE_MAPS_API_KEY` via env (já existe). **Pré-requisito:** Places API (New) habilitada no projeto. Sem a chave, o runner aborta claro. Chave nunca logada/commitada; testes injetam client fake.

## 8. Testes

- **`PlacesClient` (fake `httpx.Client` injetado, zero rede):** parse de resposta OK → `PlaceResult` (id/nome/geo/addr/primaryType); resultado sem id ou sem location → descartado; erro HTTP/rede/JSON → `[]`; confirma que reusa UM client (regressão do Errno 24).
- **`PlacesSource.venues()` (client fake):** itera semente×tipo (conta chamadas = seeds×types); mapeia `primaryType` → category ("night_club"→nightclub, "bar"→bar); `place_id` → `source_url`; `>=20` resultados dispara log de saturação; `event_pages()`/`events()` vazios.
- **Integração no pipeline (DB):** um `RawVenue` do Places com geo perto de um venue existente com nome similar → `auto_merge` (1 venue, place_id vira evidência); place_id novo distante → cria; re-run mesmo place_id → idempotente (não duplica).
- **Runner (DB, client fake):** `discover_places`/`run_ingestion` cria venues; re-run não duplica.
- Suíte backend verde. **Smoke real** (chave + Places New habilitada): rodar `python -m nightlife.discover_places`; confirmar "Supra Club Augusta" criado, N venues novos na Augusta, re-run idempotente (0 dupes via place_id), buscar a Selva no resultado.

## 9. Definition of Done

- [ ] `PlacesClient.search_nearby` (New API, field mask Pro, um Client reutilizado); parse defensivo; erro→[]; testado.
- [ ] `PlacesSource` (Source): itera semente×tipo, categoria por primaryType, place_id→source_url, log de saturação; `event_pages`/`events` vazios; testado.
- [ ] `discover_places` runner sob demanda; aborta claro sem a chave.
- [ ] Dedup verificado no pipeline (auto_merge com existente, idempotência por place_id).
- [ ] Suíte verde; smoke real: Supra Club Augusta presente, venues novos na Augusta, re-run idempotente.
