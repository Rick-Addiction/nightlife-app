# Instagram — descoberta de handles + scraper de flyers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Descobrir automaticamente os @handles de IG dos venues/organizers já no banco (tags OSM + sites + páginas Sympla) e, com uma conta burner via Playwright, varrer esses perfis baixando imagem+legenda+metadados dos posts recentes para o inbox `flyers/` — que o pipeline de visão (Plano G) já consome.

**Architecture:** Spec: `docs/superpowers/specs/2026-07-04-instagram-discovery-scraper-design.md`. Três metades: (1) **descoberta** — `extraction/social.py` puro + `ingestion/handle_discovery.py` (httpx injetável, reusa JSON-LD); (2) **scraper** — `ingestion/instagram_source.py` com parse puro (`parse_profile_posts`) isolado da casca Playwright injetável (mesma disciplina do `CodexExtractor`); (3) **extração** — `FlyerSource`/`flyer.py` estendidos para consumir o sidecar (legenda→dica, permalink→`source_url`). Ritmo conservador, tudo em config.

**Tech Stack:** Python 3.14, SQLAlchemy 2.0, psycopg3, Alembic, httpx+truststore, BeautifulSoup, Playwright (chromium), Pydantic, pytest. Postgres+PostGIS (Docker na **5434**). Codex CLI (extração de visão, já existente).

**Convenções:**
- **cwd do shell RESETA entre chamadas Bash** — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Python: `.venv/Scripts/python`. Testes: `.venv/Scripts/python -m pytest`. **A pasta temp padrão do pytest tem permissão corrompida** → sempre passe `--basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`.
- **Avast intercepta TLS** → runners que vão à rede usam `truststore.inject_into_ssl()` (já é o padrão do projeto). Playwright: `playwright install chromium` pode precisar de rede confiável; documentado na Task 12.
- Backend suite hoje = **103 testes** (não regride). Postgres precisa estar no ar (`docker compose up -d --wait`); os testes criam/dropam `nightlife_test`.
- Commits terminam com: `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`
- **NÃO** mexa em `web/`. Trabalhe em `src/nightlife/`, `tests/`, `migrations/`, e no fim `README.md`.

---

## File Structure

```
src/nightlife/
  models.py                         # + Venue.instagram/website, + IgProfileState (MODIFICA)
  config.py                         # + knobs de IG e descoberta (MODIFICA)
  extraction/
    social.py                       # NOVO — puro: handles de URL/texto/tags OSM/JSON-LD
    flyer.py                        # MODIFICA — flyer_to_raw_event(permalink=)
  ingestion/
    handle_discovery.py             # NOVO — orquestra descoberta (httpx injetável)
    instagram_source.py             # NOVO — parse puro + scraper Playwright injetável
    codex_extractor.py              # MODIFICA — extract(caption=)
    flyer_source.py                 # MODIFICA — lê sidecar, passa caption+permalink
  persistence/
    ig_state.py                     # NOVO — handles a varrer + cursor + auto-pausa
  ig_login.py                       # NOVO — bootstrap manual da sessão da burner
  discover_handles.py               # NOVO — runner da descoberta
  ingest_ig.py                      # NOVO — runner do scraper
migrations/versions/
  a1b2c3d4e5f6_instagram.py         # NOVO — migration
tests/
  test_social.py · test_handle_discovery.py · test_ig_state.py
  test_instagram_source.py · test_flyer_caption.py   # NOVOS
  test_flyer.py · test_flyer_source.py               # MODIFICA (caption/permalink)
README.md                           # MODIFICA (Task 12)
```

---

## Task 1: Modelo de dados + migration

**Files:**
- Modify: `src/nightlife/models.py`
- Create: `migrations/versions/a1b2c3d4e5f6_instagram.py`
- Test: `tests/test_models.py` (append)

- [ ] **Step 1: Teste que falha** — em `tests/test_models.py`, adicione ao final:

```python
def test_venue_has_social_fields_and_ig_state(session):
    from nightlife.models import Venue, IgProfileState

    v = Venue(name="Lab Club", instagram="labclub", website="https://labclub.com.br")
    session.add(v)
    session.flush()
    assert v.instagram == "labclub"
    assert v.website == "https://labclub.com.br"

    st = IgProfileState(handle="labclub")
    session.add(st)
    session.flush()
    assert st.consecutive_failures == 0
    assert st.last_shortcode is None
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_models.py::test_venue_has_social_fields_and_ig_state -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `ImportError` de `IgProfileState` / `Venue` sem `instagram`.

- [ ] **Step 3: Implementar** — em `src/nightlife/models.py`, na classe `Venue`, adicione os dois campos logo após `address`:

```python
    address: Mapped[str | None] = mapped_column(String(500), default=None)
    instagram: Mapped[str | None] = mapped_column(String(200), default=None)
    website: Mapped[str | None] = mapped_column(String(500), default=None)
```

E adicione a nova classe ao final do arquivo (depois de `VerificationLog`):

```python
class IgProfileState(Base):
    __tablename__ = "ig_profile_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    handle: Mapped[str] = mapped_column(String(200), unique=True)
    last_shortcode: Mapped[str | None] = mapped_column(String(50), default=None)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
```

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_models.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (o `session` fixture cria as tabelas do metadata, então o teste passa antes mesmo da migration).

- [ ] **Step 5: Migration Alembic** — crie `migrations/versions/a1b2c3d4e5f6_instagram.py`:

```python
"""instagram: venue social fields + ig_profile_states

Revision ID: a1b2c3d4e5f6
Revises: 6db320547b8b
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '6db320547b8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('venues', sa.Column('instagram', sa.String(length=200), nullable=True))
    op.add_column('venues', sa.Column('website', sa.String(length=500), nullable=True))
    op.create_table(
        'ig_profile_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('handle', sa.String(length=200), nullable=False),
        sa.Column('last_shortcode', sa.String(length=50), nullable=True),
        sa.Column('last_scraped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('handle'),
    )


def downgrade() -> None:
    op.drop_table('ig_profile_states')
    op.drop_column('venues', 'website')
    op.drop_column('venues', 'instagram')
```

- [ ] **Step 6: Aplicar migration no banco de dev**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m alembic upgrade head`
Expected: `Running upgrade 6db320547b8b -> a1b2c3d4e5f6`.

- [ ] **Step 7: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/models.py migrations/versions/a1b2c3d4e5f6_instagram.py tests/test_models.py && git commit -m "feat(ig): Venue.instagram/website + IgProfileState (modelo + migration)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: `extraction/social.py` — handles de IG (puro)

**Files:**
- Create: `src/nightlife/extraction/social.py`
- Test: `tests/test_social.py`

- [ ] **Step 1: Teste que falha** — crie `tests/test_social.py`:

```python
from nightlife.extraction.social import (
    canonical_handle, handles_from_text, handle_from_osm_tags, handle_from_jsonld,
)


def test_canonical_handle_normaliza_e_rejeita():
    assert canonical_handle("@MambaNegra") == "mambanegra"
    assert canonical_handle("instagram.com/gop_tun/") == "gop_tun"
    assert canonical_handle("https://www.instagram.com/mamba.negra?igshid=xyz") == "mamba.negra"
    assert canonical_handle("https://instagram.com/p/ABC123/") is None      # post, nao perfil
    assert canonical_handle("https://instagram.com/reel/XYZ/") is None      # reel
    assert canonical_handle("https://instagram.com/explore/") is None
    assert canonical_handle("https://mambanegra.com.br") is None            # site, nao IG
    assert canonical_handle("") is None
    assert canonical_handle(None) is None


def test_handles_from_text_pega_url_e_mencao():
    txt = "Line-up @deusa e @vhoor. Ingressos em https://www.instagram.com/mambanegra/ !"
    assert handles_from_text(txt) == {"deusa", "vhoor", "mambanegra"}
    assert handles_from_text("") == set()


def test_handle_from_osm_tags_prioriza_instagram():
    assert handle_from_osm_tags({"contact:instagram": "https://instagram.com/labclub"}) == "labclub"
    assert handle_from_osm_tags({"instagram": "@labclub"}) == "labclub"
    # so website, e website e uma URL de IG:
    assert handle_from_osm_tags({"website": "https://instagram.com/cargoclub"}) == "cargoclub"
    # website que NAO e IG -> None (nao inventa handle a partir do site proprio)
    assert handle_from_osm_tags({"website": "https://cargo.com.br"}) is None
    assert handle_from_osm_tags({}) is None


def test_handle_from_jsonld_varre_sameas():
    data = {"@type": "NightClub", "name": "Lab",
            "sameAs": ["https://facebook.com/lab", "https://www.instagram.com/lab.club/"]}
    assert handle_from_jsonld(data) == "lab.club"
    assert handle_from_jsonld({"sameAs": "https://instagram.com/soloig"}) == "soloig"
    assert handle_from_jsonld({"@graph": [{"sameAs": ["https://instagram.com/deep"]}]}) == "deep"
    assert handle_from_jsonld({"name": "sem redes"}) is None
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_social.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — módulo `social` não existe.

- [ ] **Step 3: Implementar** — crie `src/nightlife/extraction/social.py`:

```python
# src/nightlife/extraction/social.py
"""Extracao PURA de @handles de Instagram de URLs, texto, tags OSM e JSON-LD.

Sem rede, sem DB — e onde mora a testabilidade da descoberta (spec §5.1).
"""
from __future__ import annotations

import re

_IG_URL = re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/([^/?#\s]+)", re.IGNORECASE)
_MENTION = re.compile(r"@([A-Za-z0-9._]+)")
# caminhos do instagram.com que NAO sao perfil de usuario:
_NON_PROFILE = {
    "p", "reel", "reels", "explore", "stories", "tv", "accounts",
    "about", "directory", "developer", "legal", "privacy",
}
_VALID = re.compile(r"[a-z0-9._]{1,30}")


def canonical_handle(raw: str | None) -> str | None:
    """'@Foo', 'instagram.com/foo/', 'https://instagram.com/foo?igshid=..' -> 'foo'.

    Rejeita caminhos nao-perfil (/p/, /reel/, /explore) e valores que nao sao
    handle valido (ex.: um site proprio que nao e do instagram)."""
    if not raw:
        return None
    s = raw.strip()
    m = _IG_URL.search(s)
    if m:
        s = m.group(1)
    s = s.lstrip("@").strip().strip("/").lower()
    s = s.split("?")[0].split("/")[0]
    if not s or s in _NON_PROFILE:
        return None
    if not _VALID.fullmatch(s):
        return None
    return s


def handles_from_text(text: str | None) -> set[str]:
    """Todos os handles achaveis num blob de texto/HTML: URLs de IG + @mencoes."""
    if not text:
        return set()
    out: set[str] = set()
    for m in _IG_URL.finditer(text):
        h = canonical_handle(m.group(1))
        if h:
            out.add(h)
    for m in _MENTION.finditer(text):
        h = canonical_handle(m.group(1))
        if h:
            out.add(h)
    return out


_OSM_KEYS = ("contact:instagram", "instagram", "contact:website", "website")


def handle_from_osm_tags(tags: dict) -> str | None:
    """Tags OSM -> handle. Prioriza chaves de instagram; website so conta se for URL de IG."""
    for key in _OSM_KEYS:
        val = tags.get(key)
        if not val:
            continue
        h = canonical_handle(val)
        if h:
            return h
    return None


def handle_from_jsonld(data) -> str | None:
    """Varre recursivamente um no JSON-LD (dict/list/@graph) por sameAs de IG."""
    if isinstance(data, dict):
        same = data.get("sameAs")
        if isinstance(same, str):
            h = canonical_handle(same)
            if h:
                return h
        elif isinstance(same, list):
            for u in same:
                if isinstance(u, str):
                    h = canonical_handle(u)
                    if h:
                        return h
        for v in data.values():
            h = handle_from_jsonld(v)
            if h:
                return h
    elif isinstance(data, list):
        for v in data:
            h = handle_from_jsonld(v)
            if h:
                return h
    return None
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_social.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (4).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/extraction/social.py tests/test_social.py && git commit -m "feat(ig): social.py — extracao pura de @handle (URL/texto/tags OSM/JSON-LD)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: `handle_from_html` (puro) — handle a partir de uma página

**Files:**
- Create: `src/nightlife/ingestion/handle_discovery.py`
- Test: `tests/test_handle_discovery.py`

- [ ] **Step 1: Teste que falha** — crie `tests/test_handle_discovery.py`:

```python
from nightlife.ingestion.handle_discovery import handle_from_html


def test_handle_from_html_prefere_jsonld():
    html = """<html><head>
      <script type="application/ld+json">
      {"@type":"NightClub","name":"Lab","sameAs":["https://instagram.com/lab.oficial"]}
      </script></head>
      <body><a href="https://instagram.com/outro">rodape</a></body></html>"""
    assert handle_from_html(html) == "lab.oficial"


def test_handle_from_html_cai_pra_texto_quando_sem_jsonld():
    html = '<html><body><a href="https://www.instagram.com/soanchor/">IG</a></body></html>'
    assert handle_from_html(html) == "soanchor"


def test_handle_from_html_none_quando_nao_ha_ig():
    assert handle_from_html("<html><body>sem redes</body></html>") is None
    assert handle_from_html("") is None
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_handle_discovery.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — módulo/função não existe.

- [ ] **Step 3: Implementar** — crie `src/nightlife/ingestion/handle_discovery.py`:

```python
# src/nightlife/ingestion/handle_discovery.py
"""Descoberta de @handle de IG das fontes ja capturadas (spec §5.2).

Puro na leitura de HTML (handle_from_html); a orquestracao recebe um `fetch`
injetavel (Callable[str, str|None]) — testes offline, e o runner injeta httpx.
"""
from __future__ import annotations

from ..extraction.jsonld import _iter_jsonld
from ..extraction.social import handle_from_jsonld, handles_from_text


def handle_from_html(html: str | None) -> str | None:
    """Handle de IG de uma pagina: tenta JSON-LD (sameAs), cai pra texto/links."""
    if not html:
        return None
    for node in _iter_jsonld(html):
        h = handle_from_jsonld(node)
        if h:
            return h
    found = handles_from_text(html)
    return sorted(found)[0] if found else None
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_handle_discovery.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (3).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/handle_discovery.py tests/test_handle_discovery.py && git commit -m "feat(ig): handle_from_html — handle de IG de uma pagina (JSON-LD -> texto)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 4: Descoberta em venues (tags OSM via Overpass + fetch de site)

**Importante (achado no self-review):** as tags OSM **não são persistidas** no banco — a evidência guarda só o *hash* do `raw_payload` e um `extracted_fields` que o ingest OSM deixa vazio. Então a descoberta **re-consulta o Overpass uma vez** e casa por `source_url` do OSM (`https://www.openstreetmap.org/{type}/{id}`, que É guardado na `VenueSource`). O dict `osm_tags_by_url` é injetado (testes offline; o runner faz 1 chamada real ao Overpass).

**Files:**
- Modify: `src/nightlife/ingestion/osm_source.py` (helper `parse_overpass_tags`)
- Modify: `src/nightlife/ingestion/handle_discovery.py`
- Test: `tests/test_handle_discovery.py` (append)

- [ ] **Step 1: Teste que falha** — em `tests/test_handle_discovery.py`, adicione:

```python
from nightlife.ingestion.handle_discovery import discover_venue_handles
from nightlife.ingestion.osm_source import parse_overpass_tags
from nightlife.models import Venue, VenueSource

OSM_URL = "https://www.openstreetmap.org/node/1"


def _osm_venue(session, name):
    v = Venue(name=name)
    session.add(v)
    session.flush()
    session.add(VenueSource(venue_id=v.id, source_type="osm", source_url=OSM_URL))
    session.flush()
    return v


def test_parse_overpass_tags_mapeia_por_url():
    data = {"elements": [
        {"type": "node", "id": 1, "tags": {"name": "Lab", "contact:instagram": "@lab"}},
        {"type": "way", "id": 2, "tags": {"name": "Cargo"}},
    ]}
    out = parse_overpass_tags(data)
    assert out["https://www.openstreetmap.org/node/1"]["contact:instagram"] == "@lab"
    assert out["https://www.openstreetmap.org/way/2"] == {"name": "Cargo"}


def test_discover_venue_via_osm_tag(session):
    v = _osm_venue(session, "Lab Club")
    tags = {OSM_URL: {"contact:instagram": "@labclub"}}

    def fetch(url):
        raise AssertionError("fetch nao deveria ser chamado")

    n = discover_venue_handles(session, osm_tags_by_url=tags, fetch=fetch)
    session.flush()
    assert n == 1
    assert v.instagram == "labclub"


def test_discover_venue_via_site_fetch(session):
    v = _osm_venue(session, "Cargo")
    tags = {OSM_URL: {"website": "https://cargo.com.br"}}

    def fetch(url):
        assert url == "https://cargo.com.br"
        return '<html><body><a href="https://instagram.com/cargoclub">ig</a></body></html>'

    n = discover_venue_handles(session, osm_tags_by_url=tags, fetch=fetch)
    session.flush()
    assert n == 1
    assert v.instagram == "cargoclub"
    assert v.website == "https://cargo.com.br"


def test_discover_venue_idempotente(session):
    v = Venue(name="Ja Tem", instagram="jatem")
    session.add(v)
    session.flush()
    n = discover_venue_handles(session, osm_tags_by_url={}, fetch=lambda u: None)
    assert n == 0
    assert v.instagram == "jatem"  # nao sobrescreve
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_handle_discovery.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `parse_overpass_tags`/`discover_venue_handles` não existem.

- [ ] **Step 3a: Helper no `osm_source.py`** — em `src/nightlife/ingestion/osm_source.py`, adicione ao final (função pura, ao lado de `parse_overpass`):

```python
def parse_overpass_tags(data: dict) -> dict[str, dict]:
    """Mapeia source_url do OSM -> tags do elemento. A descoberta de handles usa
    isto porque as tags nao sao persistidas na evidencia (so o hash do payload)."""
    out: dict[str, dict] = {}
    for el in data.get("elements", []):
        url = f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}"
        out[url] = el.get("tags") or {}
    return out
```

- [ ] **Step 3b: Implementar em `handle_discovery.py`** — adicione os imports no topo e as funções:

```python
import logging
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..extraction.social import canonical_handle, handle_from_osm_tags
from ..models import Venue, VenueSource

_log = logging.getLogger(__name__)

Fetcher = Callable[[str], "str | None"]


def _osm_source_url(session: Session, venue_id: int) -> str | None:
    src = session.scalars(
        select(VenueSource).where(
            VenueSource.venue_id == venue_id, VenueSource.source_type == "osm"
        )
    ).first()
    return src.source_url if src is not None else None


def discover_venue_handles(
    session: Session, *, osm_tags_by_url: dict[str, dict], fetch: Fetcher
) -> int:
    """Popula venue.instagram/website p/ venues sem instagram. Retorna quantos novos.

    `osm_tags_by_url`: {source_url do OSM -> tags} (o runner monta via 1 chamada ao
    Overpass). 1) tag OSM (contact:instagram/website); 2) se ha website nao-IG,
    fetch da pagina -> handle_from_html. Idempotente: pula quem ja tem instagram."""
    count = 0
    venues = session.scalars(select(Venue).where(Venue.instagram.is_(None))).all()
    for v in venues:
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
        if handle:
            v.instagram = handle
            count += 1
    return count
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_handle_discovery.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (7).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/osm_source.py src/nightlife/ingestion/handle_discovery.py tests/test_handle_discovery.py && git commit -m "feat(ig): descoberta de handle em venues (tags OSM via Overpass + fetch de site)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 5: Descoberta em organizers (páginas Sympla) + runner

**Files:**
- Modify: `src/nightlife/ingestion/handle_discovery.py`
- Create: `src/nightlife/discover_handles.py`
- Test: `tests/test_handle_discovery.py` (append)

- [ ] **Step 1: Teste que falha** — em `tests/test_handle_discovery.py`, adicione:

```python
from nightlife.ingestion.handle_discovery import discover_organizer_handles
from nightlife.models import Event, EventSource, Organizer


def test_discover_organizer_via_sympla_page(session):
    org = Organizer(name="Mamba Negra")
    session.add(org)
    session.flush()
    ev = Event(name="Mamba", organizer_id=org.id)
    session.add(ev)
    session.flush()
    session.add(EventSource(event_id=ev.id, source_type="ticketing",
                            source_url="https://sympla.com.br/evento/mamba/123"))
    session.flush()

    def fetch(url):
        assert "sympla" in url
        return '<html><body><a href="https://instagram.com/mambanegra">ig</a></body></html>'

    n = discover_organizer_handles(session, fetch=fetch)
    session.flush()
    assert n == 1
    assert org.instagram == "mambanegra"


def test_discover_organizer_idempotente(session):
    org = Organizer(name="Ja", instagram="ja")
    session.add(org)
    session.flush()
    n = discover_organizer_handles(session, fetch=lambda u: None)
    assert n == 0
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_handle_discovery.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `discover_organizer_handles` não existe.

- [ ] **Step 3: Implementar** — em `handle_discovery.py`, adicione o import e a função:

```python
from ..models import Event, EventSource, Organizer  # junte aos imports de models


def discover_organizer_handles(session: Session, *, fetch: Fetcher) -> int:
    """Popula organizer.instagram via a pagina de detalhe da Sympla (source_url
    de um EventSource do organizer). Idempotente. Retorna quantos novos."""
    count = 0
    orgs = session.scalars(select(Organizer).where(Organizer.instagram.is_(None))).all()
    for org in orgs:
        src = session.scalars(
            select(EventSource)
            .join(Event, EventSource.event_id == Event.id)
            .where(Event.organizer_id == org.id, EventSource.source_url.is_not(None))
        ).first()
        if src is None or not src.source_url:
            continue
        try:
            handle = handle_from_html(fetch(src.source_url))
        except Exception as exc:  # noqa: BLE001 — best-effort
            _log.warning("fetch de %s falhou: %s", src.source_url, exc)
            continue
        if handle:
            org.instagram = handle
            count += 1
    return count
```

- [ ] **Step 4: Runner** — crie `src/nightlife/discover_handles.py`:

```python
# src/nightlife/discover_handles.py
"""Descobre @handles de IG dos venues/organizers ja no banco.

Uso: .venv/Scripts/python -m nightlife.discover_handles
"""
from __future__ import annotations

import truststore

truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

import httpx

from .db import SessionLocal
from .ingestion.handle_discovery import discover_organizer_handles, discover_venue_handles
from .ingestion.osm_source import OVERPASS_ENDPOINT, SP_BBOX, _build_query, parse_overpass_tags

_USER_AGENT = "nightlife-app/0.1 (uso pessoal; contato: henrique.rachti@gmail.com)"


def _fetch(url: str) -> str | None:
    try:
        resp = httpx.get(url, headers={"User-Agent": _USER_AGENT},
                         timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception:  # noqa: BLE001 — best-effort; o orquestrador loga
        return None


def _osm_tags_by_url() -> dict:
    """1 chamada ao Overpass -> {source_url do OSM: tags} (as tags nao ficam no DB)."""
    try:
        resp = httpx.post(OVERPASS_ENDPOINT, data={"data": _build_query(SP_BBOX)},
                          headers={"User-Agent": _USER_AGENT}, timeout=90.0)
        resp.raise_for_status()
        return parse_overpass_tags(resp.json())
    except Exception:  # noqa: BLE001 — sem tags OSM, cai so pra veia Sympla
        return {}


def main() -> None:
    with SessionLocal() as session:
        osm_tags = _osm_tags_by_url()
        nv = discover_venue_handles(session, osm_tags_by_url=osm_tags, fetch=_fetch)
        no = discover_organizer_handles(session, fetch=_fetch)
        session.commit()
        print(f"handles novos — venues: {nv} | organizers: {no}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_handle_discovery.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (9).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/handle_discovery.py src/nightlife/discover_handles.py tests/test_handle_discovery.py && git commit -m "feat(ig): descoberta de handle em organizers (Sympla) + runner discover_handles

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 6: `persistence/ig_state.py` — handles a varrer + cursor + auto-pausa

**Files:**
- Create: `src/nightlife/persistence/ig_state.py`
- Test: `tests/test_ig_state.py`

- [ ] **Step 1: Teste que falha** — crie `tests/test_ig_state.py`:

```python
from nightlife.models import IgProfileState, Organizer, Venue
from nightlife.persistence.ig_state import (
    handles_to_scrape, get_or_create_state, record_success, record_failure,
)


def test_handles_to_scrape_uniao_venue_organizer(session):
    session.add_all([
        Venue(name="A", instagram="a"),
        Venue(name="B", instagram="b"),
        Venue(name="Sem IG"),
        Organizer(name="C", instagram="c"),
        Organizer(name="Dup", instagram="a"),  # duplicado com o venue A
    ])
    session.flush()
    assert handles_to_scrape(session) == ["a", "b", "c"]


def test_handles_to_scrape_ignora_pausados(session):
    session.add(Venue(name="A", instagram="a"))
    session.add(IgProfileState(handle="a", consecutive_failures=3))
    session.flush()
    assert handles_to_scrape(session, pause_threshold=3) == []
    assert handles_to_scrape(session, pause_threshold=4) == ["a"]


def test_cursor_success_e_failure(session):
    st = get_or_create_state(session, "a")
    assert st.consecutive_failures == 0
    record_failure(st)
    record_failure(st)
    assert st.consecutive_failures == 2
    record_success(st, "SHORT123")
    assert st.consecutive_failures == 0
    assert st.last_shortcode == "SHORT123"
    assert st.last_scraped_at is not None
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ig_state.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar** — crie `src/nightlife/persistence/ig_state.py`:

```python
# src/nightlife/persistence/ig_state.py
"""Handles a varrer (uniao venue+organizer) e cursor de scraping por handle."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import IgProfileState, Organizer, Venue


def handles_to_scrape(session: Session, *, pause_threshold: int = 3) -> list[str]:
    """Uniao distinta e ordenada de venue.instagram e organizer.instagram,
    menos os handles pausados (falhas consecutivas >= pause_threshold)."""
    vs = session.scalars(select(Venue.instagram).where(Venue.instagram.is_not(None))).all()
    os_ = session.scalars(select(Organizer.instagram).where(Organizer.instagram.is_not(None))).all()
    paused = set(session.scalars(
        select(IgProfileState.handle).where(IgProfileState.consecutive_failures >= pause_threshold)
    ).all())
    return sorted({*vs, *os_} - paused)


def get_or_create_state(session: Session, handle: str) -> IgProfileState:
    st = session.scalars(
        select(IgProfileState).where(IgProfileState.handle == handle)
    ).first()
    if st is None:
        st = IgProfileState(handle=handle)
        session.add(st)
        session.flush()
    return st


def record_success(state: IgProfileState, last_shortcode: str | None) -> None:
    state.consecutive_failures = 0
    state.last_scraped_at = datetime.now(timezone.utc)
    if last_shortcode:
        state.last_shortcode = last_shortcode


def record_failure(state: IgProfileState) -> None:
    state.consecutive_failures += 1
    state.last_scraped_at = datetime.now(timezone.utc)
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ig_state.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (3).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/persistence/ig_state.py tests/test_ig_state.py && git commit -m "feat(ig): ig_state — handles a varrer + cursor + auto-pausa

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 7: `parse_profile_posts` + cursor incremental (puro)

**Files:**
- Create: `src/nightlife/ingestion/instagram_source.py`
- Test: `tests/test_instagram_source.py`

- [ ] **Step 1: Teste que falha** — crie `tests/test_instagram_source.py`:

```python
from nightlife.ingestion.instagram_source import IgPost, parse_profile_posts, new_posts

# Formato GraphQL simplificado que o IG carrega numa pagina de perfil.
GRAPHQL = {
    "data": {"user": {"edge_owner_to_timeline_media": {"edges": [
        {"node": {"shortcode": "P3", "taken_at_timestamp": 1717800000,
                  "display_url": "https://cdn/p3.jpg",
                  "edge_media_to_caption": {"edges": [{"node": {"text": "Sabado! @deusa"}}]}}},
        {"node": {"shortcode": "P2", "taken_at_timestamp": 1717700000,
                  "display_url": "https://cdn/p2.jpg",
                  "edge_media_to_caption": {"edges": []}}},
        {"node": {"shortcode": "P1", "taken_at_timestamp": 1717600000,
                  "display_url": "https://cdn/p1.jpg",
                  "edge_media_to_caption": {"edges": [{"node": {"text": "flyer antigo"}}]}}},
    ]}}}
}


def test_parse_profile_posts():
    posts = parse_profile_posts(GRAPHQL)
    assert [p.shortcode for p in posts] == ["P3", "P2", "P1"]
    assert posts[0].image_url == "https://cdn/p3.jpg"
    assert posts[0].caption == "Sabado! @deusa"
    assert posts[1].caption is None
    assert posts[0].taken_at == 1717800000


def test_new_posts_para_no_cursor():
    posts = parse_profile_posts(GRAPHQL)
    # ja vimos P1 antes: so P3 e P2 sao novos
    assert [p.shortcode for p in new_posts(posts, last_shortcode="P1", cap=10)] == ["P3", "P2"]


def test_new_posts_respeita_cap():
    posts = parse_profile_posts(GRAPHQL)
    assert [p.shortcode for p in new_posts(posts, last_shortcode=None, cap=2)] == ["P3", "P2"]


def test_parse_profile_posts_vazio():
    assert parse_profile_posts({}) == []
    assert parse_profile_posts({"data": {"user": None}}) == []
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_instagram_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar** — crie `src/nightlife/ingestion/instagram_source.py`:

```python
# src/nightlife/ingestion/instagram_source.py
"""Scraper de Instagram (spec §6). O PARSE do JSON do IG e puro e testavel;
a navegacao Playwright fica numa casca injetavel (Task 9), como o CodexExtractor."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IgPost:
    shortcode: str
    image_url: str
    caption: str | None
    taken_at: int | None


def _caption_of(node: dict) -> str | None:
    edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
    if edges:
        text = (edges[0].get("node") or {}).get("text")
        return text or None
    return None


def parse_profile_posts(graphql: dict) -> list[IgPost]:
    """JSON GraphQL do perfil -> lista de IgPost (mais recentes primeiro).

    Tolerante a formato ausente/None: devolve [] em vez de estourar (o IG muda
    o shape com frequencia — o fallback e melhor que quebrar o run inteiro)."""
    user = ((graphql.get("data") or {}).get("user")) or {}
    edges = ((user.get("edge_owner_to_timeline_media") or {}).get("edges")) or []
    out: list[IgPost] = []
    for edge in edges:
        node = edge.get("node") or {}
        shortcode = node.get("shortcode")
        image_url = node.get("display_url")
        if not shortcode or not image_url:
            continue
        out.append(IgPost(
            shortcode=shortcode,
            image_url=image_url,
            caption=_caption_of(node),
            taken_at=node.get("taken_at_timestamp"),
        ))
    return out


def new_posts(posts: list[IgPost], *, last_shortcode: str | None, cap: int) -> list[IgPost]:
    """Posts novos desde last_shortcode (para ao encontra-lo), limitado a cap."""
    out: list[IgPost] = []
    for p in posts:
        if last_shortcode is not None and p.shortcode == last_shortcode:
            break
        out.append(p)
        if len(out) >= cap:
            break
    return out
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_instagram_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (4).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/instagram_source.py tests/test_instagram_source.py && git commit -m "feat(ig): parse_profile_posts + new_posts (parse puro do JSON do IG + cursor)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 8: `scrape_handles` — orquestração do scraper (navegador injetável)

**Files:**
- Modify: `src/nightlife/ingestion/instagram_source.py`
- Test: `tests/test_instagram_source.py` (append)

Escreve imagem + sidecar no inbox, atualiza cursor, auto-pausa. O navegador (`fetch_posts`) e o downloader (`download`) são injetáveis — testados com fakes, sem Playwright.

- [ ] **Step 1: Teste que falha** — em `tests/test_instagram_source.py`, adicione:

```python
import json
from nightlife.ingestion.instagram_source import scrape_handle, ScrapeConfig


def test_scrape_handle_grava_imagem_e_sidecar(tmp_path):
    posts = [IgPost("P3", "https://cdn/p3.jpg", "Sabado @deusa", 1717800000),
             IgPost("P2", "https://cdn/p2.jpg", None, 1717700000)]

    def fetch_posts(handle):
        assert handle == "mambanegra"
        return posts

    downloaded = []

    def download(post, dest):  # simula baixar a imagem pro caminho dest
        dest.write_bytes(b"fakejpg")
        downloaded.append(post.shortcode)
        return dest

    cfg = ScrapeConfig(inbox=tmp_path, cap=10)
    result = scrape_handle("mambanegra", last_shortcode=None,
                           fetch_posts=fetch_posts, download=download, config=cfg)

    assert result.last_shortcode == "P3"      # mais recente vira o novo cursor
    assert downloaded == ["P3", "P2"]
    sidecar = json.loads((tmp_path / "P3.json").read_text(encoding="utf-8"))
    assert sidecar["handle"] == "mambanegra"
    assert sidecar["permalink"] == "https://www.instagram.com/p/P3/"
    assert sidecar["caption"] == "Sabado @deusa"
    assert (tmp_path / "P3.jpg").exists()


def test_scrape_handle_incremental_para_no_cursor(tmp_path):
    posts = [IgPost("P3", "u3", None, 3), IgPost("P2", "u2", None, 2), IgPost("P1", "u1", None, 1)]
    cfg = ScrapeConfig(inbox=tmp_path, cap=10)
    result = scrape_handle("h", last_shortcode="P2",
                           fetch_posts=lambda h: posts,
                           download=lambda p, d: d.write_bytes(b"x") or d, config=cfg)
    assert result.last_shortcode == "P3"          # so P3 e novo
    assert (tmp_path / "P3.jpg").exists()
    assert not (tmp_path / "P2.jpg").exists()


def test_scrape_handle_sem_posts_novos_mantem_cursor(tmp_path):
    cfg = ScrapeConfig(inbox=tmp_path, cap=10)
    result = scrape_handle("h", last_shortcode="P9",
                           fetch_posts=lambda h: [IgPost("P9", "u", None, 1)],
                           download=lambda p, d: d, config=cfg)
    assert result.last_shortcode == "P9"          # nada novo: cursor inalterado
    assert result.downloaded == 0
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_instagram_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `scrape_handle`/`ScrapeConfig` não existem.

- [ ] **Step 3: Implementar** — em `instagram_source.py`, adicione os imports no topo e o código:

```python
import json
import logging
from pathlib import Path
from typing import Callable

_log = logging.getLogger(__name__)


@dataclass
class ScrapeConfig:
    inbox: Path
    cap: int = 6


@dataclass
class ScrapeResult:
    handle: str
    last_shortcode: str | None
    downloaded: int


def _ext_from_url(url: str) -> str:
    for e in (".jpg", ".jpeg", ".png", ".webp"):
        if e in url.lower():
            return e
    return ".jpg"


def permalink_of(shortcode: str) -> str:
    return f"https://www.instagram.com/p/{shortcode}/"


def scrape_handle(
    handle: str, *, last_shortcode: str | None,
    fetch_posts: Callable[[str], list[IgPost]],
    download: Callable[[IgPost, Path], Path],
    config: ScrapeConfig,
) -> ScrapeResult:
    """Varre um handle: baixa imagem + sidecar dos posts novos no inbox.

    `fetch_posts` (navegador) e `download` (baixador) sao injetados — a casca
    Playwright real vem na Task 9; aqui a logica e testada com fakes."""
    config.inbox.mkdir(parents=True, exist_ok=True)
    posts = fetch_posts(handle)
    fresh = new_posts(posts, last_shortcode=last_shortcode, cap=config.cap)
    downloaded = 0
    for post in fresh:
        image_path = config.inbox / f"{post.shortcode}{_ext_from_url(post.image_url)}"
        try:
            download(post, image_path)
        except Exception as exc:  # noqa: BLE001 — pula o post, segue os outros
            _log.warning("download de %s falhou: %s", post.shortcode, exc)
            continue
        sidecar = config.inbox / f"{post.shortcode}.json"
        sidecar.write_text(json.dumps({
            "handle": handle,
            "permalink": permalink_of(post.shortcode),
            "caption": post.caption,
            "taken_at": post.taken_at,
        }, ensure_ascii=False), encoding="utf-8")
        downloaded += 1
    # cursor novo = o post mais recente visto (posts[0]); se nao havia posts, mantem
    new_cursor = posts[0].shortcode if posts else last_shortcode
    return ScrapeResult(handle=handle, last_shortcode=new_cursor, downloaded=downloaded)
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_instagram_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (7).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/instagram_source.py tests/test_instagram_source.py && git commit -m "feat(ig): scrape_handle — imagem+sidecar no inbox, cursor (navegador injetavel)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 9: Casca Playwright (navegador real) + `ig_login` + runner `ingest_ig`

**Files:**
- Modify: `src/nightlife/ingestion/instagram_source.py` (casca Playwright)
- Create: `src/nightlife/ig_login.py`, `src/nightlife/ingest_ig.py`
- Modify: `src/nightlife/config.py`

**Verificação:** Playwright NÃO roda em jsdom/pytest CI aqui — como o MapLibre no Plano H, esta task é verificada por **smoke manual** (Task 12), não por teste unitário. **Calibração permitida:** o formato interno do IG (endpoint GraphQL, nomes de campo, seletores) muda; ajuste `_playwright_fetch_posts`/interceptação durante o smoke até uma imagem+sidecar reais caírem no inbox — SEM alterar `parse_profile_posts`/`scrape_handle` (que os testes travam).

- [ ] **Step 1: Config** — em `src/nightlife/config.py`, adicione ao final:

```python
from pathlib import Path

# Instagram scraper (spec §8) — defaults conservadores
IG_USER_DATA_DIR = Path(os.environ.get("IG_USER_DATA_DIR", ".ig_session"))
IG_HEADFUL = os.environ.get("IG_HEADFUL", "1") != "0"
IG_MAX_PROFILES_PER_RUN = int(os.environ.get("IG_MAX_PROFILES_PER_RUN", "8"))
IG_MAX_POSTS_FIRST_SWEEP = int(os.environ.get("IG_MAX_POSTS_FIRST_SWEEP", "6"))
IG_MAX_POSTS_INCREMENTAL = int(os.environ.get("IG_MAX_POSTS_INCREMENTAL", "12"))
IG_DELAY_MIN = float(os.environ.get("IG_DELAY_MIN", "4"))
IG_DELAY_MAX = float(os.environ.get("IG_DELAY_MAX", "11"))
IG_FAILURE_PAUSE_THRESHOLD = int(os.environ.get("IG_FAILURE_PAUSE_THRESHOLD", "3"))
```

- [ ] **Step 2: Casca Playwright** — em `instagram_source.py`, adicione ao final. Isola o I/O do browser; import de `playwright` é lazy (não quebra os testes/import do módulo se o pacote não estiver instalado):

```python
def open_context(user_data_dir: Path, *, headful: bool):
    """Abre um persistent context do chromium com a sessao da burner."""
    from playwright.sync_api import sync_playwright  # lazy: so quando de fato scrapeia
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        str(user_data_dir), headless=not headful,
    )
    return pw, context


def playwright_fetch_posts(context, handle: str) -> list[IgPost]:
    """Navega ao perfil e captura as respostas JSON do IG; parse_profile_posts
    (puro, testado) filtra a que tem o timeline (spec §6.3).

    BRITTLE por natureza (o IG ofusca/muda): calibrar no smoke. Capturamos todo
    JSON e delegamos ao parse — o contrato estavel e parse_profile_posts."""
    page = context.new_page()
    captured: list[dict] = []

    def _on_response(resp):
        if "application/json" not in resp.headers.get("content-type", ""):
            return
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001 — nem toda resposta JSON e util
            return
        if isinstance(data, dict):
            captured.append(data)  # parse_profile_posts acha a que tem timeline

    page.on("response", _on_response)
    page.goto(f"https://www.instagram.com/{handle}/", wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(2500)
    posts: list[IgPost] = []
    for data in captured:
        posts = parse_profile_posts(data)
        if posts:
            break
    page.close()
    return posts


def playwright_download(context, post: IgPost, dest: Path) -> Path:
    """Baixa a imagem do post usando a sessao autenticada (cookies do context)."""
    resp = context.request.get(post.image_url, timeout=30000)
    dest.write_bytes(resp.body())
    return dest
```

> Calibração (smoke, Task 12): se o perfil não disparar uma resposta JSON com o timeline (o IG às vezes embute em `<script>` no HTML inicial), o fallback é ler `page.content()` e extrair o JSON embutido, ou rolar a página para forçar o XHR. Ajuste `playwright_fetch_posts`; **não** toque em `parse_profile_posts`.

- [ ] **Step 3: `ig_login`** — crie `src/nightlife/ig_login.py`:

```python
# src/nightlife/ig_login.py
"""Bootstrap manual da sessao da conta BURNER (uma vez).

Abre o chromium headful com user-data-dir persistente; VOCE loga a burner a mao
(2FA/challenge inclusos). A sessao fica salva e e reusada pelo ingest_ig.
Uso: .venv/Scripts/python -m nightlife.ig_login
Nenhuma credencial e digitada por codigo (regra de seguranca)."""
from __future__ import annotations

from . import config
from .ingestion.instagram_source import open_context


def main() -> None:
    config.IG_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    pw, context = open_context(config.IG_USER_DATA_DIR, headful=True)
    page = context.new_page()
    page.goto("https://www.instagram.com/accounts/login/")
    print("Loga a conta BURNER na janela do Chromium. Ao terminar, feche a janela.")
    try:
        page.wait_for_event("close", timeout=0)  # espera voce fechar a aba
    except Exception:  # noqa: BLE001
        pass
    context.close()
    pw.stop()
    print(f"Sessao salva em {config.IG_USER_DATA_DIR}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Runner `ingest_ig`** — crie `src/nightlife/ingest_ig.py`:

```python
# src/nightlife/ingest_ig.py
"""Varre os perfis de IG descobertos, baixando flyers recentes pro inbox flyers/.

Uso (apos ig_login): .venv/Scripts/python -m nightlife.ingest_ig
Ritmo conservador (spec §6): headful, delays humanos, caps de config."""
from __future__ import annotations

import random
import time
from pathlib import Path

from . import config
from .db import SessionLocal
from .ingestion.instagram_source import (
    ScrapeConfig, open_context, playwright_download, playwright_fetch_posts, scrape_handle,
)
from .persistence.ig_state import (
    get_or_create_state, handles_to_scrape, record_failure, record_success,
)

FLYERS_DIR = Path("flyers")


def main() -> None:
    FLYERS_DIR.mkdir(exist_ok=True)
    with SessionLocal() as session:
        handles = handles_to_scrape(session, pause_threshold=config.IG_FAILURE_PAUSE_THRESHOLD)
        handles = handles[: config.IG_MAX_PROFILES_PER_RUN]
        if not handles:
            print("nenhum handle a varrer (rode discover_handles primeiro).")
            return
        pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
        total = 0
        try:
            for handle in handles:
                st = get_or_create_state(session, handle)
                cap = (config.IG_MAX_POSTS_FIRST_SWEEP if st.last_shortcode is None
                       else config.IG_MAX_POSTS_INCREMENTAL)
                cfg = ScrapeConfig(inbox=FLYERS_DIR, cap=cap)
                try:
                    result = scrape_handle(
                        handle, last_shortcode=st.last_shortcode,
                        fetch_posts=lambda h: playwright_fetch_posts(context, h),
                        download=lambda p, d: playwright_download(context, p, d),
                        config=cfg,
                    )
                    record_success(st, result.last_shortcode)
                    total += result.downloaded
                    print(f"@{handle}: {result.downloaded} novas")
                except Exception as exc:  # noqa: BLE001 — falha isolada por handle
                    record_failure(st)
                    print(f"@{handle}: FALHA ({exc}) — falhas={st.consecutive_failures}")
                session.commit()
                time.sleep(random.uniform(config.IG_DELAY_MIN, config.IG_DELAY_MAX))
        finally:
            context.close()
            pw.stop()
        print(f"total baixado: {total} imagens em {FLYERS_DIR}/ "
              f"(rode ingest_flyers para extrair)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Sanidade de import (sem Playwright real)** — garante que o módulo importa e os testes seguem verdes (o import de `playwright` é lazy, então não é exigido para importar/testar):

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -c "import nightlife.ingest_ig, nightlife.ig_login; print('import ok')" && .venv/Scripts/python -m pytest tests/test_instagram_source.py tests/test_ig_state.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: `import ok` + testes PASS. (Se `import ok` falhar por causa de `from playwright...` no topo, mova o import para dentro das funções — ele deve ser lazy.)

- [ ] **Step 6: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/instagram_source.py src/nightlife/ig_login.py src/nightlife/ingest_ig.py src/nightlife/config.py && git commit -m "feat(ig): casca Playwright + ig_login (bootstrap burner) + runner ingest_ig

Navegacao/download reais (verificados por smoke manual, calibracao permitida);
parse puro e orquestracao ficam travados pelos testes.

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 10: Extração usa a legenda (permalink → source_url, caption → dica)

**Files:**
- Modify: `src/nightlife/extraction/flyer.py`
- Modify: `src/nightlife/ingestion/codex_extractor.py`
- Test: `tests/test_flyer_caption.py` (novo); `tests/test_flyer.py`/`tests/test_codex_extractor.py` rodam como regressão (não modificados)

- [ ] **Step 1: Teste que falha** — crie `tests/test_flyer_caption.py`:

```python
from datetime import date
from pathlib import Path

from nightlife.extraction.flyer import FlyerExtraction, flyer_to_raw_event
from nightlife.ingestion.codex_extractor import CodexExtractor

REF = date(2026, 6, 1)


def test_permalink_vira_source_url():
    ext = FlyerExtraction(event_name="Mamba", quotes={"event_name": "Mamba"},
                          confidence={"event_name": 0.9})
    ev = flyer_to_raw_event(ext, "hash123", reference=REF,
                            permalink="https://www.instagram.com/p/ABC/")
    assert ev is not None
    assert ev.source_url == "https://www.instagram.com/p/ABC/"


def test_sem_permalink_mantem_id_sintetico():
    ext = FlyerExtraction(event_name="Mamba", quotes={"event_name": "Mamba"},
                          confidence={"event_name": 0.9})
    ev = flyer_to_raw_event(ext, "hash123", reference=REF)
    assert ev.source_url == "flyer:hash123"


def test_caption_vai_no_prompt_do_codex():
    captured = {}

    def fake_runner(image_path, prompt):
        captured["prompt"] = prompt
        return '{"event_name": "Mamba", "quotes": {"event_name":"Mamba"}, "confidence": {"event_name":0.9}}'

    ext = CodexExtractor(runner=fake_runner)
    ext.extract(Path("f.png"), caption="Sabado 13/06 na Lab, line-up @deusa")
    assert "Sabado 13/06 na Lab" in captured["prompt"]
    assert "legenda" in captured["prompt"].lower()


def test_extract_sem_caption_funciona():
    def fake_runner(image_path, prompt):
        return '{"event_name": "X", "quotes": {"event_name":"X"}, "confidence": {"event_name":0.9}}'
    assert CodexExtractor(runner=fake_runner).extract(Path("f.png")) is not None
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_flyer_caption.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `flyer_to_raw_event` não aceita `permalink`; `extract` não aceita `caption`.

- [ ] **Step 3a: Implementar `flyer.py`** — em `src/nightlife/extraction/flyer.py`, altere a assinatura de `flyer_to_raw_event` e o `source_url`. Troque a assinatura:

```python
def flyer_to_raw_event(
    extraction: FlyerExtraction, image_hash: str, *, reference: date,
    permalink: str | None = None,
) -> RawEvent | None:
```

E na construção do `RawEvent`, troque a linha do `source_url`:

```python
        source_url=permalink or f"flyer:{image_hash}",
```

Atualize o `Protocol` `FlyerExtractor` para o novo `extract` (caption opcional):

```python
class FlyerExtractor(Protocol):
    def extract(self, image_path: Path, *, caption: str | None = None) -> FlyerExtraction | None: ...
```

- [ ] **Step 3b: Implementar `codex_extractor.py`** — em `src/nightlife/ingestion/codex_extractor.py`, altere `CodexExtractor.extract` para aceitar `caption` e injetá-la no prompt:

```python
    def extract(self, image_path: Path, *, caption: str | None = None) -> FlyerExtraction | None:
        base = _PROMPT
        if caption:
            base = (_PROMPT + "\n\nDICA — a legenda do post que acompanha o flyer diz "
                    f"(use como apoio, mas a IMAGEM manda; nao invente):\n{caption}")
        prompt = base
        for attempt in range(self._retries + 1):
            try:
                output = self._runner(image_path, prompt)
                data = _extract_json(output)
                return FlyerExtraction.model_validate(data)
            except (ValueError, json.JSONDecodeError, ValidationError,
                    subprocess.SubprocessError, OSError) as exc:
                _log.warning("extracao de %s falhou (tentativa %d): %s",
                             image_path, attempt + 1, exc)
                prompt = (base + "\n\nATENCAO: sua resposta anterior foi invalida "
                          f"({exc}). Responda APENAS com o objeto JSON.")
        return None
```

- [ ] **Step 4: Ver passar** (inclui a suíte de flyer existente, que não pode regredir)

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_flyer_caption.py tests/test_flyer.py tests/test_codex_extractor.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (todos — as chamadas antigas `extract(path)` seguem válidas porque `caption` tem default).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/extraction/flyer.py src/nightlife/ingestion/codex_extractor.py tests/test_flyer_caption.py && git commit -m "feat(ig): extracao usa legenda (permalink->source_url, caption->dica no prompt)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 11: `FlyerSource` consome o sidecar

**Files:**
- Modify: `src/nightlife/ingestion/flyer_source.py`
- Modify: `src/nightlife/ingest_flyers.py` (mover o sidecar junto)
- Test: `tests/test_flyer_source.py` (append)

- [ ] **Step 1: Teste que falha** — em `tests/test_flyer_source.py`, adicione:

```python
import json


def test_le_sidecar_e_passa_caption_e_permalink(tmp_path):
    _img(tmp_path / "P3.png", seed=5)
    (tmp_path / "P3.json").write_text(json.dumps({
        "handle": "mambanegra", "permalink": "https://www.instagram.com/p/P3/",
        "caption": "Sabado 13/06 na Lab", "taken_at": 1717800000,
    }), encoding="utf-8")

    seen = {}

    class _Extractor:
        def extract(self, image_path, *, caption=None):
            seen["caption"] = caption
            return _extraction("Mamba")

    src = FlyerSource(tmp_path, _Extractor(), reference=REF)
    events = src.events()
    assert seen["caption"] == "Sabado 13/06 na Lab"          # legenda repassada
    assert events[0].source_url == "https://www.instagram.com/p/P3/"  # permalink vira evidencia
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_flyer_source.py::test_le_sidecar_e_passa_caption_e_permalink -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `FlyerSource` ignora o sidecar; `extract` é chamado sem `caption`.

- [ ] **Step 3a: Implementar `flyer_source.py`** — reescreva o corpo do laço em `events()` para ler o sidecar. Substitua o trecho a partir de `extraction = self._extractor.extract(path)` por:

```python
            sidecar = path.with_suffix(".json")
            caption = permalink = None
            if sidecar.exists():
                try:
                    meta = json.loads(sidecar.read_text(encoding="utf-8"))
                    caption = meta.get("caption")
                    permalink = meta.get("permalink")
                except (ValueError, OSError):
                    pass

            extraction = self._extractor.extract(path, caption=caption)
            if extraction is None:
                _log.warning("flyer %s: extracao falhou (codex) — investigar", path.name)
                self.failed_paths.append(path)
                continue
            raw_event = flyer_to_raw_event(extraction, image_hash,
                                           reference=self._reference, permalink=permalink)
```

E adicione `import json` no topo de `flyer_source.py`.

- [ ] **Step 3b: Mover o sidecar junto** — em `src/nightlife/ingest_flyers.py`, faça o `_move_all` levar o sidecar `.json` junto da imagem. Substitua a função `_move_all` por:

```python
def _move_all(paths: list[Path], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for p in paths:
        for f in (p, p.with_suffix(".json")):  # imagem + sidecar (se houver)
            if not f.exists():
                continue
            target = dest / f.name
            if target.exists():
                target.unlink()
            shutil.move(str(f), str(target))
```

- [ ] **Step 4: Ver passar** (a suíte de flyer_source inteira não pode regredir)

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_flyer_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (3 — os 2 antigos + o novo; os antigos não têm sidecar, então `caption=None`, comportamento inalterado).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/flyer_source.py src/nightlife/ingest_flyers.py tests/test_flyer_source.py && git commit -m "feat(ig): FlyerSource le sidecar (caption->extracao, permalink->source_url)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 12: Suíte cheia + Playwright install + smoke manual + README

**Files:**
- Modify: `README.md`
- (sem código novo de produção)

- [ ] **Step 1: Suíte backend inteira verde**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: todos passam — 103 antigos + novos (social 4, handle_discovery 9, ig_state 3, instagram_source 7, flyer_caption 4, flyer_source +1, models +1 = +29 → ~132). Se algum número divergir, investigue antes de seguir.

- [ ] **Step 2: Instalar Playwright + chromium**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pip install playwright && .venv/Scripts/python -m playwright install chromium`
Expected: instala o browser. (Se o download falhar por TLS do Avast, tente `set NODE_TLS_REJECT_UNAUTHORIZED=0` só para o comando de install, ou baixe o chromium pela rede confiável — documente o que funcionou.)

- [ ] **Step 3: Smoke manual do scraper** (uma vez, com a burner)

```bash
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m nightlife.discover_handles   # popula handles
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m nightlife.ig_login            # loga a burner a mao
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m nightlife.ingest_ig           # varre; ve imagem+sidecar em flyers/
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m nightlife.ingest_flyers       # extrai flyer -> evento
```
Expected: `discover_handles` imprime handles novos > 0; após `ingest_ig`, `flyers/` tem `<shortcode>.jpg` + `<shortcode>.json`; `ingest_flyers` cria evento(s). **Este é o ponto de calibração** da Task 9 (interceptação do GraphQL do IG) — ajuste `playwright_fetch_posts` até uma imagem real cair no inbox, sem tocar em `parse_profile_posts`.

- [ ] **Step 4: README** — em `README.md`, adicione a seção:

```markdown
## Instagram (descoberta de handles + scraper de flyers)

Requer Playwright: `.venv/Scripts/python -m pip install playwright && .venv/Scripts/python -m playwright install chromium`.

```bash
# 1. Descobrir os @handles dos venues/organizers (tags OSM + sites + Sympla)
.venv/Scripts/python -m nightlife.discover_handles

# 2. Logar a conta BURNER (uma vez; janela do Chromium abre p/ login manual)
.venv/Scripts/python -m nightlife.ig_login

# 3. Varrer os perfis -> baixa flyers recentes (imagem + sidecar) pro inbox flyers/
.venv/Scripts/python -m nightlife.ingest_ig

# 4. Extrair os flyers baixados -> eventos no banco (pipeline de visao)
.venv/Scripts/python -m nightlife.ingest_flyers
```

Ritmo conservador (1x/dia, headful, delays humanos, caps em `config.py`). Use uma
conta **burner** (não a principal): o Instagram pode bloquear automação. Handles
com falhas repetidas são auto-pausados.
```

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add README.md && git commit -m "docs: README do fluxo de Instagram (discover_handles + ig_login + ingest_ig)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Coverage map (plano ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §4 Venue.instagram/website + IgProfileState + migration | Task 1 |
| §5.1 social.py puro (URL/texto/tags OSM/JSON-LD) | Task 2 |
| §5.2 handle_from_html + descoberta venues (OSM+site) | Tasks 3, 4 |
| §5.2 descoberta organizers (Sympla) + runner | Task 5 |
| §4/§6 handles a varrer + cursor + auto-pausa | Task 6 |
| §6.3 parse puro do JSON do IG + cursor incremental | Task 7 |
| §6.3 orquestração (imagem+sidecar, navegador injetável) | Task 8 |
| §6.1/§6.2/§6.3 casca Playwright + ig_login + runner | Task 9 |
| §7 extração usa legenda (permalink→source_url, caption→dica) | Task 10 |
| §7 FlyerSource consome sidecar | Task 11 |
| §9/§12 suíte verde + smoke manual + README | Task 12 |

**Fora deste plano (spec §10):** stories/reels vídeo, comentários, multi-conta, cron, resolver captcha, backfill de histórico.
