# Ciclo B — Instagram em Escala — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Escalar a cobertura de IG de 14 pra centenas de venues (handles extraídos dos sites oficiais do Ciclo A), varrer com rotação/prioridade sustentável pra burner (2 níveis, cota 70/30, cap 20), e gravar `ig_last_post_at` como sinal de vida (`ig_stale` >12m neutraliza `has_contact` na relevância).

**Architecture:** Estende peças existentes, sem módulo novo: `discover_venue_handles` passa a usar `venue.website` (e extrai handle direto quando o site JÁ é um perfil de IG); `ig_state` ganha `scrape_queue` (2 níveis + antiguidade + cota) e `record_venue_activity`; `ScrapeResult` ganha `latest_post_at`; relevância ganha `ig_stale`. Uma migration (`Venue.ig_last_post_at`).

**Tech Stack:** Python 3.14, SQLAlchemy 2.0, Alembic, pytest, Playwright (só no smoke real), Postgres 5434.

**Referências do código existente (verificadas):**
- `handle_discovery.discover_venue_handles(session, *, osm_tags_by_url, fetch)` — hoje: tag OSM → site da tag OSM (`website` local) → `handle_from_html(fetch(website))`; NUNCA usa `v.website`. `canonical_handle(url)` (de `extraction.social`) extrai handle de URL de IG (retorna None se não for IG).
- `ig_state`: `handles_to_scrape(session, *, pause_threshold=3) -> list[str]` (universo: venues relevant com IG + organizers, menos platform/pausados, **ordem alfabética**); `IgProfileState(handle, last_shortcode, last_scraped_at, consecutive_failures)`.
- `instagram_source`: `IgPost(shortcode, image_url, caption, taken_at: int|None)` (unix); `parse_profile_posts` (recent-first); `ScrapeResult(handle, last_shortcode, downloaded)`; `scrape_handle(handle, *, last_shortcode, fetch_posts, download, config)` — `posts = fetch_posts(handle)` já vê o topo do timeline em toda varredura.
- `ingest_ig.main()`: `handles = handles_to_scrape(...)[:config.IG_MAX_PROFILES_PER_RUN]`; loop com `get_or_create_state`/`record_success`/`record_failure`; commit por handle.
- `config.IG_MAX_PROFILES_PER_RUN = int(os.environ.get("IG_MAX_PROFILES_PER_RUN", "8"))`.
- `nightlife_relevance.venue_relevance(name, category, has_events, is_monitored, *, places_verified=False, business_status=None, source_count=1, has_contact=False)` — v2: `alive = places_verified or source_count >= 2 or has_contact`.
- `api/main.py list_venues` — bloco `if not include_all:` computa e passa os sinais v2 (ver arquivo).
- Models: `Venue(..., instagram, website, business_status, enriched_at, is_monitored)`, `Event(venue_id, organizer_id, starts_at)`, `Organizer(instagram)`. Última migration: `d4e5f6a7b8c9`.
- Testes: fixture `session`; `tests/test_handle_discovery.py` (fakes de fetch), `tests/test_ig_state.py`, `tests/test_instagram_source.py`.

**Convenção de commit:** trailer `Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu`.
**Testes:** `.venv/Scripts/python -m pytest <arquivo> -v` (Postgres 5434 de pé). Suíte completa com `--basetemp="<scratchpad>/bt"`.

---

### Task 1: extração de handle via `venue.website`

**Files:**
- Modify: `src/nightlife/ingestion/handle_discovery.py` (função `discover_venue_handles`)
- Test: `tests/test_handle_discovery.py` (adicionar 3 testes)

- [ ] **Step 1: Write the failing tests**

Adicionar ao fim de `tests/test_handle_discovery.py` (o arquivo já tem fakes de `fetch` nos testes existentes — seguir o padrão local; `Venue` já importado lá):

```python
def test_discover_venue_via_venue_website(session):
    # site oficial JA no banco (ex.: websiteUri do Places) e fonte de handle
    v = Venue(name="Selva Club", website="https://selva.club/")
    session.add(v)
    session.flush()
    html = '<a href="https://www.instagram.com/selva.011/">IG</a>'
    fetched = []
    def fetch(url):
        fetched.append(url)
        return html
    n = discover_venue_handles(session, osm_tags_by_url={}, fetch=fetch)
    assert n == 1 and v.instagram == "selva.011"
    assert fetched == ["https://selva.club/"]


def test_discover_venue_website_que_ja_e_perfil_de_ig(session):
    # muitos clubes usam o IG como site: websiteUri = instagram.com/handle
    # -> handle de graca, SEM fetch
    v = Venue(name="Bar do X", website="https://www.instagram.com/bardox/")
    session.add(v)
    session.flush()
    def fetch(url):
        raise AssertionError("nao deveria fazer fetch")
    n = discover_venue_handles(session, osm_tags_by_url={}, fetch=fetch)
    assert n == 1 and v.instagram == "bardox"


def test_discover_venue_tag_osm_vence_o_site_do_banco(session):
    # com contact:instagram na tag OSM, nem olha o venue.website
    from nightlife.persistence.evidence import record_venue_evidence
    from nightlife.persistence.inputs import SourceInfo
    v = Venue(name="Club Y", website="https://site-que-nao-deve-ser-buscado.com")
    session.add(v)
    session.flush()
    record_venue_evidence(session, v.id, SourceInfo(
        source_type="osm", source_url="https://osm.org/node/9"), contribution=20)
    def fetch(url):
        raise AssertionError("nao deveria fazer fetch")
    n = discover_venue_handles(
        session, osm_tags_by_url={"https://osm.org/node/9": {"contact:instagram": "clubey"}},
        fetch=fetch)
    assert n == 1 and v.instagram == "clubey"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_handle_discovery.py -v -k "venue_website or perfil_de_ig or vence_o_site"`
Expected: os 2 primeiros FALHAM (`n == 0`, `v.instagram is None`); o terceiro pode já passar (tag OSM já vence hoje).

- [ ] **Step 3: Write minimal implementation**

Em `discover_venue_handles`, substituir o miolo do loop (do `handle = handle_from_osm_tags(tags)` até o fim do `if handle is None ...`) por:

```python
        handle = handle_from_osm_tags(tags)
        website = tags.get("website") or tags.get("contact:website")
        if website and not v.website:
            v.website = website
        # site oficial ja no banco (ex.: websiteUri do Places, Ciclo A) tambem
        # e fonte; a tag OSM tem precedencia quando existe
        fetch_url = website or v.website
        if handle is None and fetch_url:
            handle = canonical_handle(fetch_url)   # site que JA e um perfil de IG
        if handle is None and fetch_url:
            try:
                handle = handle_from_html(fetch(fetch_url))
            except Exception as exc:  # noqa: BLE001 — fetch best-effort, nao fatal
                _log.warning("fetch de %s falhou: %s", fetch_url, exc)
```

(Os imports já existem no arquivo: `canonical_handle` já é importado de `extraction.social`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_handle_discovery.py -v`
Expected: PASS (16 testes — 13 existentes + 3 novos).

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/ingestion/handle_discovery.py tests/test_handle_discovery.py
git commit -m "feat: descoberta de handle via venue.website (sites do Ciclo A)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 2: model + migration — `Venue.ig_last_post_at`

**Files:**
- Modify: `src/nightlife/models.py` (classe `Venue`, após `enriched_at`)
- Create: `migrations/versions/e5f6a7b8c9d0_venue_ig_last_post_at.py`
- Test: `tests/test_venue_ig_activity_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_venue_ig_activity_model.py
from datetime import datetime, timezone

from nightlife.models import Venue


def test_venue_persiste_ig_last_post_at(session):
    ts = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    v = Venue(name="Selva Club", ig_last_post_at=ts)
    session.add(v)
    session.flush()
    assert session.get(Venue, v.id).ig_last_post_at == ts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_venue_ig_activity_model.py -v`
Expected: FAIL com `TypeError: 'ig_last_post_at' is an invalid keyword argument`

- [ ] **Step 3: Write minimal implementation**

Em `models.py`, classe `Venue`, adicionar após `enriched_at`:

```python
    ig_last_post_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
```

Criar `migrations/versions/e5f6a7b8c9d0_venue_ig_last_post_at.py`:

```python
"""venues: ig_last_post_at (atividade do IG como sinal de vida)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('venues', sa.Column('ig_last_post_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('venues', 'ig_last_post_at')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_venue_ig_activity_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/models.py migrations/versions/e5f6a7b8c9d0_venue_ig_last_post_at.py tests/test_venue_ig_activity_model.py
git commit -m "feat: coluna ig_last_post_at no Venue + migration

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 3: `ScrapeResult.latest_post_at`

**Files:**
- Modify: `src/nightlife/ingestion/instagram_source.py` (`ScrapeResult` + `scrape_handle`)
- Test: `tests/test_instagram_source.py` (adicionar 2 testes)

- [ ] **Step 1: Write the failing tests**

Adicionar ao fim de `tests/test_instagram_source.py` (seguir os fakes locais de `fetch_posts`/`download` já usados no arquivo; `IgPost`, `ScrapeConfig`, `scrape_handle` já importados lá — conferir e completar imports se preciso, inclusive `from datetime import datetime, timezone`):

```python
def test_scrape_reporta_latest_post_at(tmp_path):
    posts = [
        IgPost(shortcode="NEW11111111", image_url="http://x/i.jpg", caption=None,
               taken_at=1751500000),
        IgPost(shortcode="OLD11111111", image_url="http://x/j.jpg", caption=None,
               taken_at=1751000000),
    ]
    result = scrape_handle(
        "clube", last_shortcode=None,
        fetch_posts=lambda h: posts,
        download=lambda p, d: d.write_bytes(b"x") or d,
        config=ScrapeConfig(inbox=tmp_path, cap=10),
    )
    assert result.latest_post_at == datetime.fromtimestamp(1751500000, tz=timezone.utc)


def test_scrape_incremental_sem_novos_ainda_reporta_latest(tmp_path):
    # cursor no topo: nada novo pra baixar, mas o topo do timeline foi VISTO
    posts = [IgPost(shortcode="TOP11111111", image_url="http://x/i.jpg", caption=None,
                    taken_at=1751500000)]
    result = scrape_handle(
        "clube", last_shortcode="TOP11111111",
        fetch_posts=lambda h: posts,
        download=lambda p, d: d.write_bytes(b"x") or d,
        config=ScrapeConfig(inbox=tmp_path, cap=10),
    )
    assert result.downloaded == 0
    assert result.latest_post_at == datetime.fromtimestamp(1751500000, tz=timezone.utc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_instagram_source.py -v -k latest`
Expected: FAIL com `AttributeError: ... 'latest_post_at'`

- [ ] **Step 3: Write minimal implementation**

Em `instagram_source.py`:
1. Adicionar ao import: `from datetime import datetime, timezone`.
2. `ScrapeResult` ganha o campo (com default, pra não quebrar construções existentes):
```python
@dataclass
class ScrapeResult:
    handle: str
    last_shortcode: str | None
    downloaded: int
    latest_post_at: datetime | None = None
```
3. Em `scrape_handle`, logo após `posts = fetch_posts(handle)`:
```python
    # topo do timeline e visto em TODA varredura (mesmo incremental sem download):
    # vira o sinal de vida do venue (ig_last_post_at)
    ts = next((p.taken_at for p in posts if p.taken_at), None)
    latest_post_at = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
```
4. No `return`, adicionar `latest_post_at=latest_post_at`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_instagram_source.py -v`
Expected: PASS (todos — os existentes seguem verdes, o campo novo tem default).

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/ingestion/instagram_source.py tests/test_instagram_source.py
git commit -m "feat: ScrapeResult.latest_post_at (topo do timeline como sinal de vida)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 4: `scrape_queue` + `record_venue_activity` + cap 20

**Files:**
- Modify: `src/nightlife/persistence/ig_state.py`
- Modify: `src/nightlife/config.py` (default 8 → 20)
- Test: `tests/test_ig_state.py` (adicionar)

- [ ] **Step 1: Write the failing tests**

Adicionar ao fim de `tests/test_ig_state.py` (imports no topo: adicionar `scrape_queue, record_venue_activity` ao import de `ig_state`, e `from datetime import datetime, timedelta, timezone`):

```python
def _v(session, name, handle, **kw):
    v = Venue(name=name, instagram=handle, category="nightclub", **kw)
    session.add(v)
    session.flush()
    return v


def _state(session, handle, days_ago):
    st = IgProfileState(handle=handle)
    if days_ago is not None:
        st.last_scraped_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    session.add(st)
    session.flush()
    return st


def test_scrape_queue_quentes_primeiro_com_cota(session):
    futuro = datetime.now(timezone.utc) + timedelta(days=3)
    # 3 quentes (evento futuro/monitorado) + 3 frios; cap 4 -> ceil(4*0.7)=3 quentes + 1 frio
    for i, h in enumerate(["hot1", "hot2"]):
        v = _v(session, f"Hot {i}", h)
        session.add(Event(name="F", venue_id=v.id, starts_at=futuro))
    _v(session, "Hot Mon", "hot3", is_monitored=True)
    for i, h in enumerate(["cold1", "cold2", "cold3"]):
        _v(session, f"Cold {i}", h)
    session.flush()
    q = scrape_queue(session, cap=4)
    assert set(q[:3]) == {"hot1", "hot2", "hot3"}   # quentes na frente
    assert len(q) == 4 and q[3].startswith("cold")  # 1 vaga sobrou pro frio


def test_scrape_queue_antiguidade_dentro_do_nivel(session):
    for h in ["a", "b", "c"]:
        _v(session, h.upper(), h)
    _state(session, "a", days_ago=1)     # varrido ontem
    _state(session, "b", days_ago=30)    # varrido ha 1 mes
    # "c" nunca varrido (sem state)
    session.flush()
    q = scrape_queue(session, cap=3)
    assert q == ["c", "b", "a"]          # nunca-varrido primeiro, depois o mais antigo


def test_scrape_queue_quentes_excedentes_completam_vagas(session):
    futuro = datetime.now(timezone.utc) + timedelta(days=3)
    for i in range(4):                    # 4 quentes, 0 frios; cap 4
        v = _v(session, f"H{i}", f"hot{i}")
        session.add(Event(name="F", venue_id=v.id, starts_at=futuro))
    session.flush()
    q = scrape_queue(session, cap=4)
    assert len(q) == 4                    # cota nao desperdica vaga quando nao ha frio


def test_scrape_queue_organizer_com_evento_futuro_e_quente(session):
    futuro = datetime.now(timezone.utc) + timedelta(days=3)
    org = Organizer(name="Mamba", instagram="mambaorg")
    session.add(org)
    session.flush()
    session.add(Event(name="F", organizer_id=org.id, starts_at=futuro))
    _v(session, "Frio", "frio1")
    session.flush()
    q = scrape_queue(session, cap=1)
    assert q == ["mambaorg"]              # organizer quente fura a fila


def test_scrape_queue_respeita_pausados(session):
    _v(session, "A", "a")
    session.add(IgProfileState(handle="a", consecutive_failures=3))
    session.flush()
    assert scrape_queue(session, cap=5, pause_threshold=3) == []


def test_record_venue_activity_grava_no_dono_do_handle(session):
    v = _v(session, "Selva", "selva.011")
    ts = datetime(2026, 7, 1, tzinfo=timezone.utc)
    record_venue_activity(session, "selva.011", ts)
    assert v.ig_last_post_at == ts
    record_venue_activity(session, "handle_de_organizer", ts)   # nao explode, nao toca venue
    record_venue_activity(session, "selva.011", None)           # None nao apaga
    assert v.ig_last_post_at == ts
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_ig_state.py -v -k "scrape_queue or activity"`
Expected: FAIL com `ImportError: cannot import name 'scrape_queue'`

- [ ] **Step 3: Write minimal implementation**

Em `ig_state.py` — imports novos no topo: `import math`, `from zoneinfo import ZoneInfo`, e adicionar `distinct` ao import do sqlalchemy (`from sqlalchemy import distinct, select`). Adicionar ao fim do arquivo:

```python
_SP_TZ = ZoneInfo("America/Sao_Paulo")
_HOT_SHARE = 0.7   # cota da rodada reservada aos quentes (decisao do spec: 70/30)


def _hot_handles(session: Session) -> set[str]:
    """Handles 'quentes': venue monitorado OU com evento futuro; organizer com
    evento futuro. 'Futuro' = a partir de hoje em America/Sao_Paulo."""
    today = datetime.now(_SP_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    hot: set[str] = set()
    future_venues = set(session.scalars(
        select(distinct(Event.venue_id)).where(
            Event.venue_id.is_not(None), Event.starts_at >= today)))
    for v in session.scalars(select(Venue).where(Venue.instagram.is_not(None))):
        if v.is_monitored or v.id in future_venues:
            hot.add(v.instagram)
    future_orgs = set(session.scalars(
        select(distinct(Event.organizer_id)).where(
            Event.organizer_id.is_not(None), Event.starts_at >= today)))
    for o in session.scalars(select(Organizer).where(Organizer.instagram.is_not(None))):
        if o.id in future_orgs:
            hot.add(o.instagram)
    return hot


def scrape_queue(session: Session, *, cap: int, pause_threshold: int = 3) -> list[str]:
    """Fila da rodada: nivel 1 (quentes) ate 70% do cap, resto completa com
    nivel 2; dentro de cada nivel, nunca-varrido primeiro e depois o mais
    antigo (mata a ordem alfabetica que so varria os 8 primeiros)."""
    universe = handles_to_scrape(session, pause_threshold=pause_threshold)
    scraped_at = {st.handle: st.last_scraped_at
                  for st in session.scalars(select(IgProfileState))}
    epoch = datetime.min.replace(tzinfo=timezone.utc)

    def _staleness(h: str):
        ts = scraped_at.get(h)
        return (ts is not None, ts or epoch, h)

    hot_set = _hot_handles(session)
    hot = sorted((h for h in universe if h in hot_set), key=_staleness)
    cold = sorted((h for h in universe if h not in hot_set), key=_staleness)

    hot_slots = min(len(hot), math.ceil(cap * _HOT_SHARE))
    queue = hot[:hot_slots]
    queue += cold[: cap - len(queue)]
    if len(queue) < cap:                      # sobrou vaga (poucos frios):
        queue += hot[hot_slots:][: cap - len(queue)]  # quentes excedentes completam
    return queue


def record_venue_activity(session: Session, handle: str,
                          latest_post_at: "datetime | None") -> None:
    """Grava o sinal de vida do IG no(s) venue(s) donos do handle. Handle de
    organizer nao toca venue; None nao apaga valor existente."""
    if latest_post_at is None:
        return
    for v in session.scalars(select(Venue).where(Venue.instagram == handle)):
        v.ig_last_post_at = latest_post_at
```

Em `config.py`, trocar o default: `IG_MAX_PROFILES_PER_RUN = int(os.environ.get("IG_MAX_PROFILES_PER_RUN", "20"))` (comentário: `# cap por rodada (Ciclo B): ~300 handles -> passada em ~15 dias`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_ig_state.py -v`
Expected: PASS (10 testes — 4 existentes + 6 novos).

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/persistence/ig_state.py src/nightlife/config.py tests/test_ig_state.py
git commit -m "feat: scrape_queue (2 niveis, cota 70/30, antiguidade) + record_venue_activity + cap 20

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 5: fiação no `ingest_ig`

**Files:**
- Modify: `src/nightlife/ingest_ig.py`

Contexto: fiação de runner (padrão do projeto: `main()` de runner não tem teste unitário; a lógica está nas funções testadas nas Tasks 3–4). Verificação = suíte inteira verde + smoke real na Task 7.

- [ ] **Step 1: Editar `ingest_ig.py`**

1. Trocar o import de `ig_state` para incluir as funções novas:
```python
from .persistence.ig_state import (
    get_or_create_state, record_failure, record_success, record_venue_activity,
    scrape_queue,
)
```
2. Substituir as duas linhas de seleção de handles:
```python
        handles = handles_to_scrape(session, pause_threshold=config.IG_FAILURE_PAUSE_THRESHOLD)
        handles = handles[: config.IG_MAX_PROFILES_PER_RUN]
```
por:
```python
        handles = scrape_queue(session, cap=config.IG_MAX_PROFILES_PER_RUN,
                               pause_threshold=config.IG_FAILURE_PAUSE_THRESHOLD)
```
3. Logo após `record_success(st, result.last_shortcode)`, adicionar:
```python
                    record_venue_activity(session, handle, result.latest_post_at)
```

- [ ] **Step 2: Rodar a suíte inteira**

Run: `.venv/Scripts/python -m pytest --basetemp="<scratchpad>/bt" -q`
Expected: tudo verde (exit 0) — `handles_to_scrape` continua existindo (usado por `scrape_queue`), nenhum teste referencia o corte alfabético antigo.

- [ ] **Step 3: Commit**

```bash
git add src/nightlife/ingest_ig.py
git commit -m "feat: ingest_ig usa scrape_queue e grava ig_last_post_at

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 6: `ig_stale` na relevância + API

**Files:**
- Modify: `src/nightlife/domain/nightlife_relevance.py`
- Modify: `src/nightlife/api/main.py` (bloco de sinais do `list_venues`)
- Test: `tests/test_nightlife_relevance.py` + `tests/test_api.py` (adicionar 1 em cada)

- [ ] **Step 1: Write the failing tests**

Em `tests/test_nightlife_relevance.py`, adicionar:

```python
def test_ig_stale_neutraliza_so_o_contato():
    # contato com IG parado ha 12+ meses nao prova vida
    assert venue_relevance("Lab Club", "nightclub", False, False,
                           has_contact=True, ig_stale=True) == "dormant"
    # mas Google OPERATIONAL (places_verified) vence IG quieto
    assert venue_relevance("Lab Club", "nightclub", False, False,
                           places_verified=True, ig_stale=True) == "relevant"
    # e atividade vence sempre
    assert venue_relevance("Lab Club", "nightclub", True, False,
                           ig_stale=True) == "relevant"
```

Em `tests/test_api.py`, adicionar (imports de datetime já existem no arquivo; conferir `timedelta`):

```python
def test_venues_ig_stale_esconde_so_contato(session):
    from datetime import timedelta, timezone as tz
    velho = datetime.now(tz.utc) - timedelta(days=400)
    parado = Venue(name="IG Parado", category="nightclub", lat=-23.5, lng=-46.6,
                   status="operational", confidence=30, instagram="parado",
                   ig_last_post_at=velho)
    vivo = Venue(name="IG Vivo", category="nightclub", lat=-23.5, lng=-46.6,
                 status="operational", confidence=30, instagram="vivo",
                 ig_last_post_at=datetime.now(tz.utc) - timedelta(days=10))
    session.add_all([parado, vivo])
    session.flush()
    client = _client(session)
    try:
        names = [x["name"] for x in client.get("/venues").json()]
        assert "IG Vivo" in names and "IG Parado" not in names
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_nightlife_relevance.py tests/test_api.py -v -k ig_stale`
Expected: FAIL (`TypeError: unexpected keyword argument 'ig_stale'` / "IG Parado" aparece).

- [ ] **Step 3: Write minimal implementation**

Em `nightlife_relevance.py`, na assinatura de `venue_relevance`, adicionar o kwarg `ig_stale: bool = False` (após `has_contact`), e trocar a linha do `alive` por:

```python
    # IG parado ha 12+ meses: o contato nao prova vida (mas Google OPERATIONAL
    # e atividade continuam valendo)
    alive = places_verified or source_count >= 2 or (has_contact and not ig_stale)
```

Em `api/main.py`: adicionar `timedelta` ao import de datetime. No bloco `if not include_all:` de `list_venues`, antes da list comprehension:

```python
        stale_cutoff = datetime.now(timezone.utc) - timedelta(days=365)
```

E na chamada de `venue_relevance`, adicionar:

```python
                ig_stale=(v.ig_last_post_at is not None and v.ig_last_post_at < stale_cutoff),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_nightlife_relevance.py tests/test_api.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/domain/nightlife_relevance.py src/nightlife/api/main.py tests/test_nightlife_relevance.py tests/test_api.py
git commit -m "feat: ig_stale na relevancia (IG parado >12m nao corrobora contato)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 7: suíte + migration real + smoke real (CONTROLADOR)

**Files:** nenhum novo (verificação).

- [ ] **Step 1: Suítes completas**

Run: `.venv/Scripts/python -m pytest --basetemp="<scratchpad>/bt" -q` e (de `web/`) `npx vitest run`
Expected: tudo verde por exit code.

- [ ] **Step 2: Migration no banco real**

Run: `.venv/Scripts/python -m alembic upgrade head`
Expected: `d4e5f6a7b8c9 -> e5f6a7b8c9d0`.

- [ ] **Step 3: Smoke 1 — descoberta de handles (seguro, só httpx)**

Run: `.venv/Scripts/python -m nightlife.discover_handles` (background — ~275 fetches best-effort, minutos)
Expected: `handles novos — venues: N` com N dezenas+ (antes: 14 venues com IG; conferir contagem no banco depois).

- [ ] **Step 4: Smoke 2 — rodada do IG com cap reduzido (sensível: burner)**

Run: `IG_MAX_PROFILES_PER_RUN=3 .venv/Scripts/python -m nightlife.ingest_ig` (background)
Expected: fila nova prioriza quentes/nunca-varridos; flyers baixados; `ig_last_post_at` gravado nos venues varridos. **Se falhar por sessão expirada** (login IG caiu): reportar ao usuário pra rodar `python -m nightlife.ig_login` — NÃO bloqueia o merge.

- [ ] **Step 5: Verificações (SQL)**

- `SELECT count(*) FROM venues WHERE instagram IS NOT NULL` — subiu de 14 pra N.
- `SELECT name, ig_last_post_at FROM venues WHERE ig_last_post_at IS NOT NULL` — os varridos do smoke 2.
- `GET /venues` — contagem de pins estável ou maior (handles novos não removem ninguém; ig_stale só age quando houver dado velho).

- [ ] **Step 6: Commit de ajustes do smoke (se houver)**

```bash
git add -A
git commit -m "chore: ajustes do smoke do Ciclo B

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

## Notas de implementação

- **Zero rede nos testes** (fakes de `fetch`/`fetch_posts`/`download`); Playwright só no smoke 2.
- **`handles_to_scrape` continua público e testado** — `scrape_queue` o usa como universo; os 4 testes existentes de `ig_state` ficam intactos.
- **Campos novos com default** (`ScrapeResult.latest_post_at`, kwarg `ig_stale`) — construções existentes não quebram.
- **Comparação tz-aware:** `last_scraped_at`/`ig_last_post_at` são `DateTime(timezone=True)` (Postgres devolve aware — verificado no Ciclo A); o `epoch` usado no sort é aware.
- **Smoke 2 é o único passo que toca a burner** — cap 3 de propósito; a rodada cheia de 20 fica pro daily.
