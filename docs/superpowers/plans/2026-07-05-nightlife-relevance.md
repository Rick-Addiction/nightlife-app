# Relevância de venues (precisão da descoberta) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classificar venues em `blocked`/`relevant`/`dormant` (buffet/festa-infantil vs vida noturna) e aplicar nas bordas (descoberta, scraper, API) para tirar buffets e handles de plataforma do app. Não-destrutivo.

**Architecture:** Spec: `docs/superpowers/specs/2026-07-05-nightlife-relevance-design.md`. Um módulo PURO `domain/nightlife_relevance.py` (blocklists + `venue_relevance`) consumido nas bordas: descoberta pula buffet e descarta platform-handle; `handles_to_scrape` só relevant; `/venues` esconde blocked+dormant (com `include_all`), `/events` esconde eventos de venue-buffet. Um runner de limpeza opt-in zera handles-lixo já gravados.

**Tech Stack:** Python 3.14, SQLAlchemy 2.0, FastAPI, pytest. Postgres+PostGIS (Docker 5434).

**Convenções:**
- **cwd do shell RESETA entre chamadas Bash** — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Python: `.venv/Scripts/python`. Testes: `.venv/Scripts/python -m pytest ... --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife` (SEMPRE esse basetemp).
- Suíte backend hoje = **137**. Postgres no ar. Commits terminam com trailer `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`.
- **NÃO** mexa em `web/`.

---

## File Structure

```
src/nightlife/
  domain/nightlife_relevance.py   # NOVO — puro: blocklists + venue_relevance
  ingestion/handle_discovery.py   # MODIFICA — pula buffet, descarta platform-handle
  persistence/ig_state.py         # MODIFICA — handles_to_scrape so relevant
  api/main.py                     # MODIFICA — /venues relevant (include_all), /events esconde buffet
  cleanup_relevance.py            # NOVO — runner opt-in de limpeza
tests/
  test_nightlife_relevance.py     # NOVO
  test_handle_discovery.py · test_ig_state.py · test_api.py · test_cleanup_relevance.py  # MODIFICA/NOVO
```

---

## Task 1: `domain/nightlife_relevance.py` (puro)

**Files:** Create `src/nightlife/domain/nightlife_relevance.py`; Create `tests/test_nightlife_relevance.py`

- [ ] **Step 1: Teste que falha** — crie `tests/test_nightlife_relevance.py`:

```python
from nightlife.domain.nightlife_relevance import (
    is_buffet_name, is_platform_handle, venue_relevance,
)


def test_is_buffet_name():
    assert is_buffet_name("Buffet Planeta 1")
    assert is_buffet_name("Kairós Bistrô Buffet Infantil")
    assert is_buffet_name("FantastiKids Unidade III")          # 'kids'
    assert is_buffet_name("Célia Salão de Festas & Buffet")    # acento/case
    assert not is_buffet_name("Carioca Club")
    assert not is_buffet_name("Lab Club")
    assert not is_buffet_name(None)


def test_is_platform_handle():
    assert is_platform_handle("sympla")
    assert is_platform_handle("ifoodbrasil")
    assert is_platform_handle("Facebook")                      # case-insensitive
    assert not is_platform_handle("mambanegra")
    assert not is_platform_handle(None)


def test_venue_relevance():
    assert venue_relevance("Lab Club", "nightclub", False, False) == "relevant"
    assert venue_relevance("Buffet X", "nightclub", True, True) == "blocked"   # precedencia
    assert venue_relevance("Espaco Y", "events_venue", False, False) == "dormant"
    assert venue_relevance("Espaco Y", "events_venue", True, False) == "relevant"  # tem evento
    assert venue_relevance("Espaco Z", "events_venue", False, True) == "relevant"  # monitorado
    assert venue_relevance("Sem Cat", None, False, False) == "dormant"
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_nightlife_relevance.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar** — crie `src/nightlife/domain/nightlife_relevance.py`:

```python
# src/nightlife/domain/nightlife_relevance.py
"""Relevancia de venue: 'isto e vida noturna?' (spec §3). Puro, sem DB.

blocked (buffet/festa-infantil, nunca) tem precedencia; relevant (nightclub, ou
com evento, ou monitorado); dormant (o resto — events_venue/sem-cat sem evento)."""
from __future__ import annotations

import unicodedata


def _norm(s: str | None) -> str:
    """lowercase + sem acento, p/ casar palavras robustamente."""
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


_BUFFET_KEYWORDS = (
    "buffet", "bufe", "infantil", "kids", "salao de festa", "aniversario",
    "festa infantil",
)


def is_buffet_name(name: str | None) -> bool:
    n = _norm(name)
    return any(kw in n for kw in _BUFFET_KEYWORDS)


_PLATFORM_HANDLES = frozenset({
    "sympla", "ifood", "ifoodbrasil", "facebook", "whatsapp", "instagram",
    "youtube", "tiktok", "linktr", "linktree",
})


def is_platform_handle(handle: str | None) -> bool:
    return (handle or "").lower() in _PLATFORM_HANDLES


def venue_relevance(name: str | None, category: str | None,
                    has_events: bool, is_monitored: bool) -> str:
    """'blocked' | 'relevant' | 'dormant'. blocked tem precedencia sobre tudo."""
    if is_buffet_name(name):
        return "blocked"
    if category == "nightclub" or has_events or is_monitored:
        return "relevant"
    return "dormant"
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_nightlife_relevance.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (3).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/domain/nightlife_relevance.py tests/test_nightlife_relevance.py && git commit -m "feat(relevance): nightlife_relevance.py — buffet/platform blocklist + venue_relevance

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: Descoberta pula buffet e descarta platform-handle

**Files:** Modify `src/nightlife/ingestion/handle_discovery.py`; append em `tests/test_handle_discovery.py`

- [ ] **Step 1: Teste que falha** — em `tests/test_handle_discovery.py`, ADICIONE ao final:

```python
def test_discover_venue_pula_buffet(session):
    v = _osm_venue(session, "Buffet Planeta 1")
    tags = {OSM_URL: {"contact:instagram": "@buffetplaneta"}}
    n = discover_venue_handles(session, osm_tags_by_url=tags, fetch=lambda u: None)
    session.flush()
    assert n == 0
    assert v.instagram is None            # buffet nem e considerado


def test_discover_venue_descarta_platform_handle(session):
    v = _osm_venue(session, "Casa X")
    tags = {OSM_URL: {"contact:instagram": "@sympla"}}
    n = discover_venue_handles(session, osm_tags_by_url=tags, fetch=lambda u: None)
    session.flush()
    assert n == 0
    assert v.instagram is None            # sympla e handle de plataforma


def test_discover_organizer_descarta_platform_handle(session):
    org = Organizer(name="Org Y")
    session.add(org)
    session.flush()
    ev = Event(name="E", organizer_id=org.id)
    session.add(ev)
    session.flush()
    session.add(EventSource(event_id=ev.id, source_type="ticketing",
                            source_url="https://sympla.com.br/evento/y/9"))
    session.flush()
    n = discover_organizer_handles(
        session,
        fetch=lambda u: '<a href="https://instagram.com/sympla">x</a>')
    session.flush()
    assert n == 0
    assert org.instagram is None
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_handle_discovery.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — buffet e sympla ainda seriam gravados.

- [ ] **Step 3: Implementar** — em `src/nightlife/ingestion/handle_discovery.py`:

Adicione o import (junto dos outros de `..domain`/`..extraction`):
```python
from ..domain.nightlife_relevance import is_buffet_name, is_platform_handle
```

Em `discover_venue_handles`, no início do laço `for v in venues:`, pule buffet; e troque a gravação para descartar platform-handle. O laço fica:
```python
    for v in venues:
        if is_buffet_name(v.name):
            continue                                  # buffet: nem descobre nem fetch
        url = _osm_source_url(session, v.id)
        tags = osm_tags_by_url.get(url, {}) if url else {}
        handle = handle_from_osm_tags(tags)
        website = tags.get("website") or tags.get("contact:website")
        if website and not v.website:
            v.website = website
        if handle is None and website and canonical_handle(website) is None:
            try:
                handle = handle_from_html(fetch(website))
            except Exception as exc:  # noqa: BLE001 — fetch best-effort, nao fatal
                _log.warning("fetch de %s falhou: %s", website, exc)
        if handle and not is_platform_handle(handle):
            v.instagram = handle
            count += 1
```

Em `discover_organizer_handles`, troque o bloco final `if handle:` por:
```python
        if handle and not is_platform_handle(handle):
            org.instagram = handle
            count += 1
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_handle_discovery.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (todos — os anteriores + 3 novos; os antigos não usam buffet/plataforma, seguem verdes).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/handle_discovery.py tests/test_handle_discovery.py && git commit -m "feat(relevance): descoberta pula buffet e descarta platform-handle (sympla/ifood)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: `handles_to_scrape` só venues relevant

**Files:** Modify `src/nightlife/persistence/ig_state.py`; Modify `tests/test_ig_state.py`

**Nota:** os 2 testes existentes de `handles_to_scrape` usam venues SEM categoria (que agora viram `dormant` → fora). Este task ATUALIZA esses testes para refletir a nova semântica (venues precisam ser relevant).

- [ ] **Step 1: Atualizar/adicionar testes** — em `tests/test_ig_state.py`, SUBSTITUA `test_handles_to_scrape_uniao_venue_organizer` e `test_handles_to_scrape_ignora_pausados` por:

```python
def test_handles_to_scrape_so_venues_relevant(session):
    session.add_all([
        Venue(name="Club A", instagram="a", category="nightclub"),        # relevant
        Venue(name="Espaco B", instagram="b", is_monitored=True),         # relevant (monitorado)
        Venue(name="Dormente D", instagram="d", category="events_venue"), # dormant -> fora
        Venue(name="Buffet E", instagram="e", category="events_venue"),   # blocked -> fora
        Organizer(name="C", instagram="c"),                               # organizer entra
        Organizer(name="Plataforma", instagram="sympla"),                 # platform -> fora
    ])
    session.flush()
    assert handles_to_scrape(session) == ["a", "b", "c"]


def test_handles_to_scrape_venue_com_evento_vira_relevant(session):
    v = Venue(name="Espaco F", instagram="f", category="events_venue")    # sem evento = dormant
    session.add(v)
    session.flush()
    assert handles_to_scrape(session) == []
    session.add(Event(name="Festa", venue_id=v.id, status="scheduled"))   # agora tem evento
    session.flush()
    assert handles_to_scrape(session) == ["f"]                            # promovido a relevant


def test_handles_to_scrape_ignora_pausados(session):
    session.add(Venue(name="A", instagram="a", category="nightclub"))     # relevant
    session.add(IgProfileState(handle="a", consecutive_failures=3))
    session.flush()
    assert handles_to_scrape(session, pause_threshold=3) == []
    assert handles_to_scrape(session, pause_threshold=4) == ["a"]
```

E garanta o import de `Event` no topo do arquivo de teste (junto de `IgProfileState, Organizer, Venue`):
```python
from nightlife.models import Event, IgProfileState, Organizer, Venue
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ig_state.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `handles_to_scrape` ainda não filtra por relevância (retorna d/e/sympla).

- [ ] **Step 3: Implementar** — em `src/nightlife/persistence/ig_state.py`, adicione os imports e reescreva `handles_to_scrape`:

```python
from ..domain.nightlife_relevance import is_platform_handle, venue_relevance
from ..models import Event, IgProfileState, Organizer, Venue
```
(junte `Event` ao import de models existente.)

```python
def handles_to_scrape(session: Session, *, pause_threshold: int = 3) -> list[str]:
    """Handles a varrer: handles de venues RELEVANT (nightclub/com-evento/monitorado)
    uniao com os de organizers, menos platform-handles e menos os pausados."""
    venues = session.scalars(select(Venue).where(Venue.instagram.is_not(None))).all()
    with_events = set(session.scalars(
        select(Event.venue_id).where(Event.venue_id.is_not(None))
    ).all())
    vhandles = {
        v.instagram for v in venues
        if venue_relevance(v.name, v.category, v.id in with_events, v.is_monitored) == "relevant"
    }
    ohandles = set(session.scalars(
        select(Organizer.instagram).where(Organizer.instagram.is_not(None))
    ).all())
    handles = {h for h in (vhandles | ohandles) if h and not is_platform_handle(h)}
    paused = set(session.scalars(
        select(IgProfileState.handle).where(IgProfileState.consecutive_failures >= pause_threshold)
    ).all())
    return sorted(handles - paused)
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ig_state.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (4 — 3 de handles + o de cursor intacto).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/persistence/ig_state.py tests/test_ig_state.py && git commit -m "feat(relevance): scraper so varre handles de venues relevant (buffet/dormant fora)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 4: API — `/venues` só relevant (include_all), `/events` esconde venue-buffet

**Files:** Modify `src/nightlife/api/main.py`; Modify `tests/test_api.py`

**Nota:** `test_venues_sorted_by_effective_confidence_desc` usa venues sem categoria (viram dormant → sumiriam). Este task ATUALIZA esse teste (venues viram `nightclub`) e adiciona os novos.

- [ ] **Step 1: Atualizar/adicionar testes** — em `tests/test_api.py`:

(a) troque, em `test_venues_sorted_by_effective_confidence_desc`, as duas linhas de `Venue(...)` por (adiciona `category="nightclub"` → relevant):
```python
    a = Venue(name="Fraco", status="operational", confidence=30, category="nightclub")
    b = Venue(name="Forte", status="operational", confidence=80, category="nightclub")
```

(b) ADICIONE ao final do arquivo:
```python
def test_venues_esconde_dormant_e_buffet_por_padrao(session):
    session.add_all([
        Venue(name="Club Real", category="nightclub", status="operational", confidence=60),
        Venue(name="Espaco Dormente", category="events_venue", status="operational", confidence=60),
        Venue(name="Buffet Kids", category="events_venue", status="operational", confidence=60),
    ])
    session.flush()
    client = _client(session)
    try:
        names = [x["name"] for x in client.get("/venues").json()]
        assert names == ["Club Real"]                       # dormant e buffet escondidos
        all_names = [x["name"] for x in client.get("/venues", params={"include_all": "true"}).json()]
        assert set(all_names) == {"Club Real", "Espaco Dormente", "Buffet Kids"}
    finally:
        app.dependency_overrides.clear()


def test_events_esconde_evento_de_venue_buffet(session):
    from datetime import datetime as _dt
    buf = Venue(name="Buffet Festas", status="operational", confidence=60)
    club = Venue(name="Club Z", category="nightclub", status="operational", confidence=60)
    session.add_all([buf, club]); session.flush()
    e_buf = Event(name="Aniversario", starts_at=_dt(2099, 6, 1, 22, tzinfo=SP),
                  venue_id=buf.id, status="scheduled", confidence=60)
    e_club = Event(name="Rave", starts_at=_dt(2099, 6, 1, 23, tzinfo=SP),
                   venue_id=club.id, status="scheduled", confidence=60)
    session.add_all([e_buf, e_club]); session.flush()
    client = _client(session)
    try:
        names = [x["name"] for x in client.get("/events").json()]
        assert "Rave" in names and "Aniversario" not in names   # evento de buffet escondido
        all_names = [x["name"] for x in client.get("/events", params={"include_all": "true"}).json()]
        assert "Aniversario" in all_names
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_api.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — API ainda não filtra relevância (dormant/buffet aparecem; `include_all` inexistente).

- [ ] **Step 3: Implementar** — em `src/nightlife/api/main.py`:

Adicione o import (junto de `from ..models import Event, Venue`):
```python
from ..domain.nightlife_relevance import is_buffet_name, venue_relevance
```

Em `list_venues`, adicione o parâmetro `include_all: bool = False` e o filtro de relevância. A função fica:
```python
@app.get("/venues", response_model=list[VenueOut])
def list_venues(
    type: str | None = None,
    bbox: str | None = None,
    min_confidence: int = 0,
    include_all: bool = False,
    session: Session = Depends(get_session),
):
    q = select(Venue).where(Venue.confidence >= min_confidence)
    if type is not None:
        q = q.where(Venue.category == type)
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = _parse_bbox(bbox)
        q = q.where(
            Venue.lat >= min_lat, Venue.lat <= max_lat,
            Venue.lng >= min_lng, Venue.lng <= max_lng,
        )
    venues = session.scalars(q).all()
    if not include_all:
        with_events = set(session.scalars(
            select(Event.venue_id).where(Event.venue_id.is_not(None))
        ).all())
        venues = [
            v for v in venues
            if venue_relevance(v.name, v.category, v.id in with_events, v.is_monitored) == "relevant"
        ]
    now = datetime.now(timezone.utc)
    outs = [_with_effective(VenueOut, v, now) for v in venues]
    outs = [o for o in outs if o.effective_confidence >= min_confidence]
    outs.sort(key=lambda o: o.effective_confidence, reverse=True)
    return outs
```

Em `list_events`, adicione `include_all: bool = False` e, no final, esconda eventos de venue-buffet. A cauda da função (a partir do `now =`) fica:
```python
    now = datetime.now(timezone.utc)
    outs = [_with_effective(EventOut, e, now)
            for e in session.scalars(q.order_by(Event.starts_at)).all()]
    outs = [o for o in outs if o.effective_confidence >= min_confidence]
    if not include_all:
        blocked_ids = {v.id for v in session.scalars(select(Venue)).all() if is_buffet_name(v.name)}
        outs = [o for o in outs if o.venue_id not in blocked_ids]
    return outs
```
(assinatura de `list_events` ganha `include_all: bool = False` antes de `session`.)

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_api.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (todos — os atualizados + 2 novos).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/api/main.py tests/test_api.py && git commit -m "feat(relevance): /venues esconde dormant+buffet (include_all), /events esconde buffet

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 5: Runner de limpeza opt-in (não-destrutivo)

**Files:** Create `src/nightlife/cleanup_relevance.py`; Create `tests/test_cleanup_relevance.py`

- [ ] **Step 1: Teste que falha** — crie `tests/test_cleanup_relevance.py`:

```python
from nightlife.cleanup_relevance import cleanup
from nightlife.models import Event, Organizer, Venue


def test_cleanup_zera_handle_de_buffet_e_plataforma(session):
    vb = Venue(name="Buffet Alegria", instagram="buffetalegria")   # buffet -> zera
    vok = Venue(name="Club Bom", instagram="clubbom", category="nightclub")  # fica
    op = Organizer(name="Plat", instagram="sympla")                # platform -> zera
    ook = Organizer(name="Real", instagram="mambanegra")           # fica
    session.add_all([vb, vok, op, ook])
    session.flush()
    e = Event(name="Aniv", venue_id=vb.id, status="scheduled")     # evento em buffet
    session.add(e)
    session.flush()

    cleared_v, cleared_o, buffet_events = cleanup(session)
    session.flush()
    assert cleared_v == 1 and vb.instagram is None
    assert vok.instagram == "clubbom"                              # nao mexe no bom
    assert cleared_o == 1 and op.instagram is None
    assert ook.instagram == "mambanegra"
    assert buffet_events == 1                                       # reporta, NAO deleta
    assert session.get(Event, e.id) is not None                    # evento continua no banco
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_cleanup_relevance.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar** — crie `src/nightlife/cleanup_relevance.py`:

```python
# src/nightlife/cleanup_relevance.py
"""Limpa handles-lixo ja gravados (buffet + platform) e reporta eventos de buffet.
NAO-destrutivo: nao deleta venue nem evento; so zera instagram-lixo.
Uso: .venv/Scripts/python -m nightlife.cleanup_relevance
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .domain.nightlife_relevance import is_buffet_name, is_platform_handle
from .models import Event, Organizer, Venue


def cleanup(session: Session) -> tuple[int, int, int]:
    """Zera venue.instagram de buffet/plataforma e organizer.instagram de plataforma.
    Retorna (venues_limpos, organizers_limpos, eventos_em_venue_buffet)."""
    cleared_v = cleared_o = 0
    for v in session.scalars(select(Venue).where(Venue.instagram.is_not(None))).all():
        if is_buffet_name(v.name) or is_platform_handle(v.instagram):
            v.instagram = None
            cleared_v += 1
    for o in session.scalars(select(Organizer).where(Organizer.instagram.is_not(None))).all():
        if is_platform_handle(o.instagram):
            o.instagram = None
            cleared_o += 1
    buffet_ids = [v.id for v in session.scalars(select(Venue)).all() if is_buffet_name(v.name)]
    buffet_events = 0
    if buffet_ids:
        buffet_events = len(session.scalars(
            select(Event).where(Event.venue_id.in_(buffet_ids))
        ).all())
    return cleared_v, cleared_o, buffet_events


def main() -> None:
    with SessionLocal() as session:
        cv, co, be = cleanup(session)
        session.commit()
        print(f"handles-lixo zerados — venues: {cv} | organizers: {co}")
        print(f"eventos em venue-buffet (nao deletados; escondidos pela API): {be}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_cleanup_relevance.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (1).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/cleanup_relevance.py tests/test_cleanup_relevance.py && git commit -m "feat(relevance): runner cleanup_relevance — zera handles-lixo (nao-destrutivo)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 6: Suíte cheia + limpeza real + verificação do efeito

**Files:** nenhum de produção novo.

- [ ] **Step 1: Suíte backend inteira verde**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: todos passam — 137 antigos + novos (nightlife_relevance 3, handle_discovery +3, ig_state +1 líquido, api +2, cleanup 1). Se algum número divergir, investigue antes de seguir.

- [ ] **Step 2: Rodar a limpeza no banco real (não-destrutivo)**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m nightlife.cleanup_relevance`
Expected: imprime quantos handles-lixo foram zerados (buffet + sympla/ifood) e quantos eventos de buffet existem. (Ordem de grandeza: alguns handles zerados.)

- [ ] **Step 3: Verificar o efeito na API (mapa mais limpo)**

Run:
```bash
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -c "
from fastapi.testclient import TestClient
from nightlife.api.main import app
c = TestClient(app)
rel = len(c.get('/venues').json())
allv = len(c.get('/venues', params={'include_all': 'true'}).json())
print(f'venues relevant (mapa): {rel} | total: {allv} | escondidos: {allv - rel}')
print('eventos (default):', len(c.get('/events').json()))
"
```
Expected: `relevant` bem menor que `total` (esconde buffets + dormant events_venue) — o mapa da UI fica nightclub-cêntrico. Cole a saída.

- [ ] **Step 4: Commit (se algo de doc precisar)** — não há código; se quiser, registre nada. (Sem commit obrigatório neste task.)

---

## Coverage map (plano ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §3 modelo de relevância (blocked/relevant/dormant) + blocklists | Task 1 |
| §4 descoberta pula buffet + descarta platform-handle | Task 2 |
| §4 scraper `handles_to_scrape` só relevant | Task 3 |
| §4 `/venues` relevant (include_all) + `/events` esconde buffet | Task 4 |
| §5 limpeza opt-in não-destrutiva | Task 5 |
| §6/§9 suíte verde + efeito verificado (mapa limpo) | Task 6 |

**Fora deste plano (spec §8):** classificador ML/LLM, deletar venues, reclassificar organizers, mudar a query do OSM.
