# Ciclo E-3: Detector via Feed "Seguindo" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar a varredura cega de IG por um detector: a burner aquecida segue os venues, lê o feed "Seguindo" a cada 45min (10h–02h), detecta posts novos por handle, busca só o post e joga no intérprete do E-1. Varredura atual vira reconciliação semanal.

**Architecture:** Spec `docs/superpowers/specs/2026-07-13-e3-feed-detector-design.md`. Reusa a plomberia Playwright existente (`instagram_source`: captura JSON do IG, não DOM). Peças novas: `feed_source.py` (parse do JSON do feed + fetch da sessão), `follow_source.py` (fila + ação de follow), runners `watch_feed.py`/`follow_venues.py`. O fetch dirigido baixa o post no inbox `flyers/` e reusa `post_flow.process_inbox` (E-1) — zero reescrita do intérprete. **Task 1 é um PROBE que captura o shape real do JSON do feed — é o gate; o parser (Task 2) se ancora na fixture que o probe salva.**

**Tech Stack:** Python 3.14 + Playwright (sync) + SQLAlchemy 2 + Alembic + pytest. Sem dependência nova.

**Referências verificadas do código atual (2026-07-13, branch `feat/e3-feed-detector`):**
- `ingestion/instagram_source.py`: NÃO faz DOM scraping — captura respostas JSON e parseia. `IgPost{shortcode, image_url, caption: str|None, taken_at: int|None}`. Helpers de nó tolerantes a shape moderno+legado: `_shortcode_of` (`code`|`shortcode`), `_image_of` (`image_versions2.candidates[0].url`|`display_url`), `_caption_of` (`caption.text`|`edge_media_to_caption`), `_taken_at_of` (`taken_at`|`taken_at_timestamp`). `_edges(graphql)` acha o timeline (moderno `xdt_api__v1__feed__user_timeline_graphql_connection.edges` ou legado `user.edge_owner_to_timeline_media.edges`). `parse_profile_posts(graphql)->list[IgPost]`, `new_posts(posts, *, last_shortcode, cap)`, `permalink_of(shortcode)`, `open_context(user_data_dir, *, headful)->(pw, context)`, `playwright_fetch_posts(context, handle)->list[IgPost]` (captura JSON via `page.on("response")`, `goto` do perfil, wait networkidle), `playwright_download(context, post, dest)->Path` (via `context.request.get`), `scrape_handle(...)`, `ScrapeConfig{inbox, cap}`, `ScrapeResult{downloaded, last_shortcode, latest_post_at}`.
- `persistence/ig_state.py`: `IgProfileState{handle, last_shortcode, last_scraped_at, consecutive_failures}` (+ `ig_last_post_at` no Venue). `handles_to_scrape`, `scrape_queue(cap)`, `get_or_create_state(session, handle)`, `record_success(state, last_shortcode)`, `record_failure(state)`, `record_venue_activity(session, handle, latest_post_at)`, `_hot_handles(session)->set[str]` (venue monitorado/evento-futuro; organizer evento-futuro), `handles_in_area(...)` (D-1).
- `ingestion/post_flow.py`: `process_inbox(session, inbox, interpreter, *, reference, log=print)->FlowStats`, `move_all(paths, dest)`. `PostInterpreter()` de `ingestion/post_interpreter.py`.
- `ingest_ig.py::main`: `open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)` → loop `scrape_handle` → commit + sleep. `ingest_flyers.py::main`: `process_inbox` + move.
- `daily.py`: `STEPS` = discover_handles → ingest_ra → ingest_sympla → geocode_venues → ingest_ig → ingest_flyers. `run_daily(steps,*,run,log)`, `_run_step` (subprocess+timeout), `main` (log `logs/daily.log`). `scripts/register_daily_task.ps1` (Task Scheduler diário).
- `config.py`: `IG_USER_DATA_DIR` (`.ig_session`), `IG_HEADFUL`, `IG_MAX_PROFILES_PER_RUN` (20), `IG_MAX_POSTS_*`, `IG_DELAY_MIN/MAX` (4/11), `IG_FAILURE_PAUSE_THRESHOLD` (3). Modelos importam `truststore` no runner.
- Migrations: última é `f6a7b8c9d0e1` (area_sweeps, D-1). Alembic autogenera OU escreve à mão no padrão de `migrations/versions/e5f6a7b8c9d0_*`.
- Testes: `.venv/Scripts/python -m pytest <arq> -v` (Postgres `docker compose up -d --wait`; suíte/tmp_path com `--basetemp=.pytest-tmp`, deletar; fixture `session`). **NUNCA chamar IG real em teste.**

**Convenção de commit:** trailer `Claude-Session: b9eb4ce7-361b-434d-9809-31614b56e56d`. **Branch:** `feat/e3-feed-detector`. **Conta:** burner ANTIGA aquecida (`.ig_session/`), não a @radarsp.noite.

---

### Task 1: PROBE do feed (gate — captura o JSON real, decide viabilidade)

**Files:**
- Create: `src/nightlife/probe_feed.py`, `tests/fixtures/` (dir p/ a captura)

Este é um PROBE assistido (roda com o usuário, burner logada), não TDD. Entrega: a fixture JSON do feed + um veredito.

- [ ] **Step 1: Escrever o probe**

```python
# src/nightlife/probe_feed.py
"""PROBE (Ciclo E-3, gate): abre a sessao da burner, vai ao feed, captura TODAS
as respostas JSON e salva as que parecem timeline de feed. Objetivo: descobrir o
shape (chave da connection + onde vem o @autor de cada post) pra ancorar o
parser. NAO roda em CI — e uma investigacao manual assistida.

Uso: .venv/Scripts/python -m nightlife.probe_feed
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .ingestion.instagram_source import open_context

OUT = Path("tests/fixtures")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
    captured: list[dict] = []
    try:
        page = context.new_page()

        def _on_response(resp):
            if "application/json" not in resp.headers.get("content-type", ""):
                return
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                return
            if isinstance(data, dict):
                captured.append(data)

        page.on("response", _on_response)
        # feed cronologico "Seguindo": a URL exata pode mudar — o smoke confirma.
        # /?variant=following e o caminho atual do feed "Seguindo" no web.
        page.goto("https://www.instagram.com/?variant=following",
                  wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(4000)
        page.mouse.wheel(0, 3000)          # rola pra puxar mais itens
        page.wait_for_timeout(3000)
        page.close()
    finally:
        context.close()
        pw.stop()

    # salva as respostas que tem cara de feed (heuristica ampla: mencionam
    # 'feed' ou 'timeline' nas chaves) — o humano inspeciona depois
    hits = [d for d in captured
            if any(k for k in _keys(d) if "feed" in k or "timeline" in k)]
    (OUT / "feed_probe_raw.json").write_text(
        json.dumps(hits[:5], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"capturei {len(captured)} respostas JSON; {len(hits)} com cara de feed.")
    print(f"salvo em {OUT / 'feed_probe_raw.json'} — inspecione o shape.")


def _keys(d, depth=0):
    if depth > 4 or not isinstance(d, dict):
        return
    for k, v in d.items():
        yield k
        if isinstance(v, dict):
            yield from _keys(v, depth + 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Rodar o probe COM O USUÁRIO** (burner logada, headful)

Run: `.venv/Scripts/python -m nightlife.probe_feed`
Inspecionar `tests/fixtures/feed_probe_raw.json`. Identificar: (a) a chave da connection do feed (provável `xdt_api__v1__feed__timeline` ou similar), (b) onde em cada nó vem o **@username do autor** (no timeline de PERFIL não existe; no FEED existe — provável `node.user.username` ou `node.owner.username`), (c) shortcode e taken_at (devem ser os mesmos `code`/`taken_at`).

- [ ] **Step 3: Salvar a fixture mínima pro parser**

A partir do raw, extrair 2-3 nós reais e montar `tests/fixtures/feed_sample.json` — o JSON MÍNIMO que o parser vai consumir (a connection + edges com nós de handles diferentes). Anonimizar não é necessário (dados públicos), mas manter pequeno.

- [ ] **Step 4: VEREDITO (gate)** — anotar no report:
  - Feed JSON tem connection + @autor por nó parseáveis → **segue o plano** (Task 2+).
  - Feed não serve JSON útil mas a central de notificações (`/notifications` ou o painel de atividades) serve → **replanejar detector p/ notificações** (mesmo resto do pipeline; avisar o usuário).
  - Nenhum → **ABORTA o E-3**, mantém a varredura como principal, reporta ao usuário.

- [ ] **Step 5: Commit** (o probe + a fixture; NÃO commitar `feed_probe_raw.json` se tiver dado sensível — só o `feed_sample.json` curado)

```bash
git add src/nightlife/probe_feed.py tests/fixtures/feed_sample.json
git commit -m "feat: probe do feed Seguindo (gate E-3) + fixture do shape real do JSON"
```

---

### Task 2: `parse_feed_items` (puro, ancorado na fixture do probe)

**Files:**
- Create: `src/nightlife/ingestion/feed_source.py`
- Test: `tests/test_feed_source.py`

**PRÉ:** Task 1 concluída; `tests/fixtures/feed_sample.json` existe e você conhece a connection-key e o path do @autor. Os literais abaixo assumem o shape MODERNO provável (`node.user.username`, connection `xdt_api__v1__feed__timeline`); **ajuste os seletores ao que o probe achou** — a fixture é a fonte da verdade.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feed_source.py
import json
from pathlib import Path

from nightlife.ingestion.feed_source import FeedItem, parse_feed_items

FIXTURE = json.loads((Path("tests/fixtures/feed_sample.json")).read_text(encoding="utf-8"))


def test_parse_feed_items_extrai_handle_shortcode_taken_at():
    items = parse_feed_items(FIXTURE)
    assert len(items) >= 2
    first = items[0]
    assert isinstance(first, FeedItem)
    assert first.handle          # @autor nao-vazio (o que o timeline de perfil NAO tem)
    assert first.shortcode
    assert first.taken_at is not None


def test_parse_feed_items_ignora_json_sem_feed():
    assert parse_feed_items({"data": {"outra_coisa": 1}}) == []


def test_parse_feed_items_pula_no_sem_autor_ou_shortcode():
    # anuncios/sugestoes no feed nao tem owner util — devem ser pulados
    bad = {"data": {"xdt_api__v1__feed__timeline": {"edges": [
        {"node": {"code": "SC1"}},                      # sem autor
        {"node": {"user": {"username": "selva.011"}}},  # sem shortcode
    ]}}}
    assert parse_feed_items(bad) == []
```

- [ ] **Step 2: Run** → FAIL (módulo não existe)

- [ ] **Step 3: Implement** (ajustar `_FEED_KEYS` e `_handle_of` ao shape do probe)

```python
# src/nightlife/ingestion/feed_source.py
"""Feed 'Seguindo' como fonte de deteccao (Ciclo E-3). Reusa os helpers de no
do instagram_source (shape moderno+legado); a diferenca do timeline de PERFIL e
que cada no do FEED carrega o @autor. parse_feed_items e PURO (fixture do probe)."""
from __future__ import annotations

from dataclasses import dataclass

from .instagram_source import _shortcode_of, _taken_at_of

# chave(s) da connection do feed — CONFIRMADAS no probe (Task 1). Se o shape
# real diferir, ajuste esta lista (e o test) pra bater com a fixture.
_FEED_KEYS = ("xdt_api__v1__feed__timeline",
              "xdt_api__v1__feed__timeline_connection")


@dataclass
class FeedItem:
    handle: str
    shortcode: str
    taken_at: int | None


def _feed_edges(graphql: dict) -> list:
    data = graphql.get("data") or {}
    for k in _FEED_KEYS:
        conn = data.get(k)
        if isinstance(conn, dict) and conn.get("edges"):
            return conn["edges"]
    return []


def _handle_of(node: dict) -> str | None:
    for key in ("user", "owner"):
        u = node.get(key)
        if isinstance(u, dict) and u.get("username"):
            return u["username"]
    return None


def parse_feed_items(graphql: dict) -> list[FeedItem]:
    out: list[FeedItem] = []
    for edge in _feed_edges(graphql):
        node = edge.get("node") or {}
        handle = _handle_of(node)
        shortcode = _shortcode_of(node)
        if not handle or not shortcode:      # anuncio/sugestao sem autor ou code
            continue
        out.append(FeedItem(handle=handle, shortcode=shortcode,
                            taken_at=_taken_at_of(node)))
    return out
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat(ig): parse_feed_items — extrai handle/shortcode/taken_at do JSON do feed`

---

### Task 3: `new_since_cursor` (puro — filtra por cursor por-handle)

**Files:**
- Modify: `src/nightlife/ingestion/feed_source.py`
- Test: `tests/test_feed_source.py` (acrescentar)

- [ ] **Step 1: Failing tests**

```python
def test_new_since_cursor_primeiro_poll_devolve_tudo():
    from nightlife.ingestion.feed_source import FeedItem, new_since_cursor
    items = [FeedItem("selva.011", "SC2", 200), FeedItem("blitzhaus", "BH1", 100)]
    novos = new_since_cursor(items, cursor_by_handle={})
    assert {i.shortcode for i in novos} == {"SC2", "BH1"}


def test_new_since_cursor_para_no_shortcode_ja_visto():
    from nightlife.ingestion.feed_source import FeedItem, new_since_cursor
    # feed vem do mais novo pro mais antigo; SC1 e o cursor de selva
    items = [FeedItem("selva.011", "SC2", 200), FeedItem("selva.011", "SC1", 100),
             FeedItem("selva.011", "SC0", 50)]
    novos = new_since_cursor(items, cursor_by_handle={"selva.011": "SC1"})
    assert [i.shortcode for i in novos] == ["SC2"]   # so o mais novo que SC1


def test_new_since_cursor_handle_sem_novidade():
    from nightlife.ingestion.feed_source import FeedItem, new_since_cursor
    items = [FeedItem("selva.011", "SC1", 100)]
    assert new_since_cursor(items, cursor_by_handle={"selva.011": "SC1"}) == []
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (append em `feed_source.py`):

```python
def new_since_cursor(items: list[FeedItem],
                     cursor_by_handle: dict[str, str]) -> list[FeedItem]:
    """Itens mais novos que o ultimo shortcode visto de cada handle. O feed vem
    do mais novo pro mais antigo, entao pra cada handle paramos ao bater no
    cursor. Handle sem cursor (nunca visto) -> todos os seus itens sao novos."""
    seen_cursor: set[str] = set()
    out: list[FeedItem] = []
    for it in items:
        cur = cursor_by_handle.get(it.handle)
        if cur is not None and (it.shortcode == cur or it.handle in seen_cursor):
            seen_cursor.add(it.handle)     # deste handle pra baixo e tudo antigo
            continue
        out.append(it)
    return out
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat(ig): new_since_cursor — filtra o feed pelo cursor por-handle`

---

### Task 4: `follow_queue` + coluna `IgProfileState.followed_at`

**Files:**
- Modify: `src/nightlife/models.py` (IgProfileState), `src/nightlife/persistence/ig_state.py`
- Create: `migrations/versions/a7b8c9d0e1f2_ig_followed_at.py`
- Test: `tests/test_ig_state.py` (acrescentar)

- [ ] **Step 1: Modelo + migration**

`models.py` — em `IgProfileState`, acrescente:
```python
    followed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
```
Migration `a7b8c9d0e1f2_ig_followed_at.py` (down_revision `f6a7b8c9d0e1`, padrão dos arquivos vizinhos):
```python
def upgrade() -> None:
    op.add_column("ig_profile_states",
                  sa.Column("followed_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column("ig_profile_states", "followed_at")
```
Aplicar: `.venv/Scripts/python -m alembic upgrade head`.

- [ ] **Step 2: Failing test** (em `tests/test_ig_state.py`)

```python
def test_follow_queue_nao_seguidos_quentes_primeiro_e_cap(session):
    from datetime import datetime, timezone
    from nightlife.persistence.ig_state import follow_queue, get_or_create_state
    from nightlife.models import Event, Venue
    quente = Venue(name="Blitz Haus", instagram="blitzhaus", lat=-23.55, lng=-46.65,
                   confidence=50)
    frio = Venue(name="Bar X", instagram="barx", lat=-23.55, lng=-46.65, confidence=50)
    ja_seg = Venue(name="Seguido", instagram="jaseg", lat=-23.55, lng=-46.65, confidence=50)
    session.add_all([quente, frio, ja_seg])
    session.flush()
    # quente tem evento futuro
    session.add(Event(name="Festa", status="scheduled", confidence=50, venue_id=quente.id,
                      starts_at=datetime(2099, 1, 1, tzinfo=timezone.utc)))
    st = get_or_create_state(session, "jaseg")
    st.followed_at = datetime.now(timezone.utc)   # ja seguido -> fora da fila
    session.flush()

    fila = follow_queue(session, cap=10)

    assert "jaseg" not in fila
    assert fila[0] == "blitzhaus"          # quente primeiro
    assert set(fila) == {"blitzhaus", "barx"}


def test_follow_queue_respeita_cap(session):
    from nightlife.persistence.ig_state import follow_queue
    from nightlife.models import Venue
    for i in range(5):
        session.add(Venue(name=f"V{i}", instagram=f"v{i}", lat=-23.55, lng=-46.65, confidence=50))
    session.flush()
    assert len(follow_queue(session, cap=3)) == 3
```

- [ ] **Step 3: Run** → FAIL. **Step 4: Implement** em `ig_state.py`:

```python
def follow_queue(session: Session, *, cap: int) -> list[str]:
    """Handles de venues AINDA NAO seguidos pela burner, quentes primeiro (mesmo
    criterio de _hot_handles), depois por id (ordem de descoberta). Reusa
    IgProfileState.followed_at como marca. So venues com instagram, nao-platform."""
    from ..domain.nightlife_relevance import is_platform_handle
    followed = set(session.scalars(
        select(IgProfileState.handle).where(IgProfileState.followed_at.is_not(None))).all())
    hot = _hot_handles(session)
    rows = session.scalars(
        select(Venue).where(Venue.instagram.is_not(None)).order_by(Venue.id)).all()
    seen: set[str] = set()
    cand: list[tuple[int, str]] = []       # (0=quente,1=frio, handle) preservando ordem
    for v in rows:
        h = v.instagram
        if h in followed or h in seen or is_platform_handle(h):
            continue
        seen.add(h)
        cand.append((0 if h in hot else 1, h))
    cand.sort(key=lambda t: t[0])          # estavel: quentes antes, resto na ordem de id
    return [h for _, h in cand][:cap]
```

- [ ] **Step 5: Run** → PASS. **Step 6: Commit** `feat(ig): follow_queue + IgProfileState.followed_at (migration a7b8c9d0e1f2)`

---

### Task 5: Runner `follow_venues` (Playwright, núcleo injetável)

**Files:**
- Create: `src/nightlife/follow_venues.py`, `src/nightlife/ingestion/follow_source.py`
- Test: `tests/test_follow_source.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_follow_source.py
from datetime import datetime, timezone

from nightlife.ingestion.follow_source import run_follows
from nightlife.models import IgProfileState, Venue


def test_run_follows_marca_followed_at_e_para_no_checkpoint(session):
    for h in ("aura", "quebrado", "naoalcanca"):
        session.add(Venue(name=h, instagram=h, lat=-23.55, lng=-46.65, confidence=50))
    session.flush()
    seguidos = []

    class Checkpoint(Exception):
        pass

    def fake_follow(handle):
        if handle == "quebrado":
            raise Checkpoint("challenge_required")     # checkpoint -> auto-pausa
        seguidos.append(handle)

    n = run_follows(session, ["aura", "quebrado", "naoalcanca"],
                    follow=fake_follow, delay=lambda: None,
                    checkpoint_exc=Checkpoint)

    assert seguidos == ["aura"]                       # parou ANTES de naoalcanca
    assert n == 1
    st = session.query(IgProfileState).filter_by(handle="aura").one()
    assert st.followed_at is not None
    # quebrado NAO recebe followed_at (nao seguiu)
    assert session.query(IgProfileState).filter_by(handle="quebrado").one().followed_at is None
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**:

```python
# src/nightlife/ingestion/follow_source.py
"""Nucleo do follow (Ciclo E-3): segue handles um a um, marca followed_at,
AUTO-PAUSA no 1o checkpoint (a acao de escrita mais vigiada — parar cedo protege
a burner). follow/delay injetaveis: teste offline."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from ..persistence.ig_state import get_or_create_state


def run_follows(session: Session, handles: list[str], *, follow: Callable[[str], None],
                delay: Callable[[], None], checkpoint_exc: type[BaseException]) -> int:
    seguidos = 0
    for handle in handles:
        try:
            follow(handle)
        except checkpoint_exc:
            break                          # auto-pausa: nao insiste apos challenge
        except Exception:                  # noqa: BLE001 — falha isolada (perfil sumiu etc.)
            continue
        st = get_or_create_state(session, handle)
        st.followed_at = datetime.now(timezone.utc)
        session.commit()
        seguidos += 1
        delay()
    return seguidos
```

```python
# src/nightlife/follow_venues.py
"""Segue os venues da fila pela burner aquecida (Ciclo E-3). Ramp-up lento.
Uso: .venv/Scripts/python -m nightlife.follow_venues"""
from __future__ import annotations

import random
import time

from . import config
from .db import SessionLocal
from .ingestion.follow_source import run_follows
from .ingestion.instagram_source import open_context
from .persistence.ig_state import follow_queue


class CheckpointDetected(Exception):
    pass


def _playwright_follow_factory(context):
    def _follow(handle: str) -> None:
        page = context.new_page()
        try:
            page.goto(f"https://www.instagram.com/{handle}/",
                      wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(1500)
            if "challenge" in page.url or "/accounts/suspended" in page.url:
                raise CheckpointDetected(page.url)
            # botao "Seguir" — o texto varia (Seguir/Follow); casa por role+nome.
            # SELETOR A CONFIRMAR no smoke (o IG muda o DOM).
            btn = page.get_by_role("button", name=lambda n: n and n.strip() in
                                   ("Seguir", "Follow"))
            btn.first.click(timeout=8000)
            page.wait_for_timeout(1500)
        finally:
            page.close()
    return _follow


def main() -> None:
    with SessionLocal() as session:
        handles = follow_queue(session, cap=config.IG_MAX_FOLLOWS_PER_RUN)
        if not handles:
            print("nada a seguir (todos os venues com handle ja seguidos).")
            return
        pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
        try:
            n = run_follows(
                session, handles,
                follow=_playwright_follow_factory(context),
                delay=lambda: time.sleep(random.uniform(config.IG_DELAY_MIN,
                                                        config.IG_DELAY_MAX)),
                checkpoint_exc=CheckpointDetected)
        finally:
            context.close()
            pw.stop()
        print(f"segui {n}/{len(handles)} (auto-pausa no 1o checkpoint).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run** `.venv/Scripts/python -m pytest tests/test_follow_source.py -v` → PASS. **Step 5: Commit** `feat: follow_venues — segue a fila pela burner com auto-pausa em checkpoint`

---

### Task 6: Runner `watch_feed` (detector encadeado)

**Files:**
- Create: `src/nightlife/watch_feed.py`
- Modify: `src/nightlife/ingestion/feed_source.py` (shell `playwright_fetch_feed`)
- Test: `tests/test_watch_feed.py`

- [ ] **Step 1: Failing tests** (núcleo `detect_and_fetch` injetável)

```python
# tests/test_watch_feed.py
from datetime import time as dtime

from nightlife.ingestion.feed_source import FeedItem
from nightlife.models import IgProfileState, Venue
from nightlife.watch_feed import detect_and_fetch, in_window


def test_in_window_janela_noturna():
    assert in_window(dtime(11, 0), start=10, end=2) is True
    assert in_window(dtime(1, 0), start=10, end=2) is True      # madrugada ate 02h
    assert in_window(dtime(5, 0), start=10, end=2) is False


def test_detect_and_fetch_baixa_novos_e_atualiza_cursor(session):
    v = Venue(name="Selva", instagram="selva.011", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    items = [FeedItem("selva.011", "SC2", 200), FeedItem("selva.011", "SC1", 100)]
    baixados = []

    n = detect_and_fetch(
        session, items,
        fetch=lambda handle, shortcode: baixados.append((handle, shortcode)),
        cursor_by_handle={"selva.011": "SC1"})

    assert baixados == [("selva.011", "SC2")]           # so o novo
    assert n == 1
    st = session.query(IgProfileState).filter_by(handle="selva.011").one()
    assert st.last_shortcode == "SC2"                   # cursor avancou pro topo


def test_detect_and_fetch_sem_novos_e_noop(session):
    v = Venue(name="Selva", instagram="selva.011", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    items = [FeedItem("selva.011", "SC1", 100)]
    n = detect_and_fetch(session, items, fetch=lambda h, s: None,
                         cursor_by_handle={"selva.011": "SC1"})
    assert n == 0
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**:

`feed_source.py` — shell de captura (espelha `playwright_fetch_posts`, no fim do arquivo):
```python
def playwright_fetch_feed(context) -> list[FeedItem]:
    """Abre o feed 'Seguindo' e captura o JSON; parse_feed_items (puro) extrai.
    BRITTLE (o IG muda): a URL/rolagem sao calibradas no probe/smoke."""
    page = context.new_page()
    captured: list[dict] = []

    def _on_response(resp):
        if "application/json" not in resp.headers.get("content-type", ""):
            return
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return
        if isinstance(data, dict):
            captured.append(data)

    page.on("response", _on_response)
    page.goto("https://www.instagram.com/?variant=following",
              wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(3000)
    page.mouse.wheel(0, 3000)
    page.wait_for_timeout(2500)
    page.close()
    items: list[FeedItem] = []
    for data in captured:
        got = parse_feed_items(data)
        if got:
            items = got
            break
    return items
```

`watch_feed.py`:
```python
# src/nightlife/watch_feed.py
"""Detector do feed 'Seguindo' (Ciclo E-3): le o feed, acha posts novos por
handle (cursor), baixa so esses posts e roda o intérprete do E-1. So age na
janela noturna. Uso (agendado 45min): .venv/Scripts/python -m nightlife.watch_feed"""
from __future__ import annotations

from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import select

from . import config
from .db import SessionLocal
from .ingestion.feed_source import FeedItem, new_since_cursor, playwright_fetch_feed
from .ingestion.instagram_source import open_context, permalink_of
from .models import IgProfileState, Venue
from .persistence.ig_state import get_or_create_state

_SP_TZ = ZoneInfo("America/Sao_Paulo")
FLYERS_DIR = Path("flyers")


def in_window(now: dtime, *, start: int, end: int) -> bool:
    """Janela que cruza a meia-noite (start=10, end=2 => 10h ate 02h)."""
    if start <= end:
        return start <= now.hour < end
    return now.hour >= start or now.hour < end


def detect_and_fetch(session, items: list[FeedItem], *,
                     fetch: Callable[[str, str], None],
                     cursor_by_handle: dict[str, str]) -> int:
    """Baixa os posts novos e avanca o cursor por handle pro shortcode do topo."""
    novos = new_since_cursor(items, cursor_by_handle)
    # so venues que temos no catalogo (o feed pode ter contas seguidas a mais)
    known = set(session.scalars(select(Venue.instagram)
                                .where(Venue.instagram.is_not(None))).all())
    top_by_handle: dict[str, str] = {}
    n = 0
    for it in novos:
        if it.handle not in known:
            continue
        fetch(it.handle, it.shortcode)
        top_by_handle.setdefault(it.handle, it.shortcode)  # 1o = mais novo
        n += 1
    for handle, top in top_by_handle.items():
        get_or_create_state(session, handle).last_shortcode = top
    session.commit()
    return n


def _real_fetch_factory(context):
    from .ingestion.instagram_source import IgPost, playwright_download
    import json as _json

    def _fetch(handle: str, shortcode: str) -> None:
        # baixa a imagem do permalink e grava sidecar (mesmo contrato do ingest_ig)
        FLYERS_DIR.mkdir(exist_ok=True)
        page = context.new_page()
        try:
            page.goto(permalink_of(shortcode), wait_until="networkidle", timeout=45000)
            img_url = page.locator('meta[property="og:image"]').first.get_attribute(
                "content", timeout=5000)
            caption = page.locator('meta[property="og:title"]').first.get_attribute(
                "content", timeout=5000)
        finally:
            page.close()
        if not img_url:
            return
        post = IgPost(shortcode=shortcode, image_url=img_url, caption=caption, taken_at=None)
        dest = FLYERS_DIR / f"{shortcode}.jpg"
        playwright_download(context, post, dest)
        (FLYERS_DIR / f"{shortcode}.json").write_text(
            _json.dumps({"handle": handle, "caption": caption,
                         "permalink": permalink_of(shortcode)}, ensure_ascii=False),
            encoding="utf-8")
    return _fetch


def main() -> None:
    now = datetime.now(_SP_TZ)
    if not in_window(now.time(), start=config.FEED_WINDOW_START_HOUR,
                     end=config.FEED_WINDOW_END_HOUR):
        print(f"fora da janela ({now:%H:%M} SP) — nada a fazer.")
        return
    with SessionLocal() as session:
        cursor = {st.handle: st.last_shortcode for st in
                  session.scalars(select(IgProfileState)) if st.last_shortcode}
        pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
        try:
            items = playwright_fetch_feed(context)
            n = detect_and_fetch(session, items,
                                 fetch=_real_fetch_factory(context),
                                 cursor_by_handle=cursor)
        finally:
            context.close()
            pw.stop()
        print(f"feed: {len(items)} itens, {n} posts novos baixados pro inbox.")
    # extrai os posts novos pelo intérprete do E-1 (mesmo inbox)
    if n:
        from .ingest_flyers import main as _extract
        _extract()


if __name__ == "__main__":
    main()
```

(Nota: o `_real_fetch_factory` usa `og:image`/`og:title` da página do post — SELETOR A CONFIRMAR no smoke; se o IG não servir og tags autenticado, cair pro `playwright_fetch_posts` do perfil filtrando pelo shortcode. O núcleo `detect_and_fetch` é o que os testes cobrem.)

- [ ] **Step 4: Run** `.venv/Scripts/python -m pytest tests/test_watch_feed.py -v --basetemp=.pytest-tmp` → PASS. **Step 5: Commit** `feat: watch_feed — detector do feed encadeia deteccao->fetch->interprete E-1`

---

### Task 7: Config + rebaixar varredura + agendamento

**Files:**
- Modify: `src/nightlife/config.py`, `src/nightlife/daily.py`, `tests/test_daily.py`
- Create: `scripts/register_feed_tasks.ps1`

- [ ] **Step 1: Config** — em `config.py`:
```python
IG_MAX_FOLLOWS_PER_RUN = int(os.environ.get("IG_MAX_FOLLOWS_PER_RUN", "18"))
FEED_WINDOW_START_HOUR = int(os.environ.get("FEED_WINDOW_START_HOUR", "10"))
FEED_WINDOW_END_HOUR = int(os.environ.get("FEED_WINDOW_END_HOUR", "2"))
```

- [ ] **Step 2: Failing test** (em `tests/test_daily.py`) — a varredura sai do daily; segue discover/ra/sympla/geocode/flyers:
```python
def test_ingest_ig_saiu_do_daily_diario():
    # E-3: a varredura cega vira reconciliacao SEMANAL, fora do daily das 05h
    from nightlife.daily import STEPS
    nomes = [nome for nome, argv in STEPS]
    assert "ingest_ig" not in nomes
    assert "ingest_flyers" in nomes          # extracao do inbox continua diaria
    assert "discover_handles" in nomes
```

- [ ] **Step 3: Run** → FAIL. **Step 4: Implement** — em `daily.py::STEPS`, remova a linha do `ingest_ig` (deixe discover_handles, ingest_ra, ingest_sympla, geocode_venues, ingest_flyers).

- [ ] **Step 5: Script de agendamento** `scripts/register_feed_tasks.ps1` (UTF-8 **com BOM** — PowerShell 5.1; sem acento em código pra segurança):
```powershell
# Registra as tarefas do Ciclo E-3 (o usuario roda 1x, sem admin).
# watch_feed a cada 45min; follow_venues 1x/dia; ingest_ig (reconciliacao) semanal.
param([string]$Python = ".venv\Scripts\python.exe")
$root = (Resolve-Path ".").Path
function New-NlTask($name, $module, $trigger) {
  $action = New-ScheduledTaskAction -Execute $Python -Argument "-m $module" -WorkingDirectory $root
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable) -Force | Out-Null
  Write-Host "registrada: $name"
}
# watch_feed: a cada 45min o dia todo; o runner sai sozinho fora da janela 10-02h
$t = New-ScheduledTaskTrigger -Once -At (Get-Date) `
     -RepetitionInterval (New-TimeSpan -Minutes 45) -RepetitionDuration (New-TimeSpan -Days 3650)
New-NlTask "Nightlife-WatchFeed" "nightlife.watch_feed" $t
New-NlTask "Nightlife-Follow" "nightlife.follow_venues" (New-ScheduledTaskTrigger -Daily -At 14:00)
New-NlTask "Nightlife-Reconcile" "nightlife.ingest_ig" (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 06:00)
Write-Host "pronto. (o daily das 05h continua pelo register_daily_task.ps1)"
```

- [ ] **Step 6: Run** `.venv/Scripts/python -m pytest tests/test_daily.py -v` → PASS. **Step 7: Commit** `feat: config do feed + ingest_ig sai do daily (vira reconciliacao semanal) + register_feed_tasks.ps1`

---

### Task 8: Final — suítes + smoke real (assistido/usuário)

- [ ] **Step 1:** Suíte completa: `.venv/Scripts/python -m pytest -q --basetemp=.pytest-tmp` (delete depois) → verde.
- [ ] **Step 2 (smoke assistido — burner logada):** rodar `follow_venues` com cap baixo (`IG_MAX_FOLLOWS_PER_RUN=3`) e conferir no IG que os 3 venues foram seguidos + `followed_at` gravado; conferir auto-pausa não disparou à toa.
- [ ] **Step 3 (smoke assistido):** com ~5 venues seguidos e algum tendo postado, rodar `watch_feed` na janela e conferir: itens do feed parseados, post novo baixado pro inbox, `ingest_flyers` extraiu, evento no banco, cursor avançou.
- [ ] **Step 4 (usuário):** registrar as tarefas (`powershell -ExecutionPolicy Bypass -File scripts\register_feed_tasks.ps1`) + deixar o ramp-up de follows rodar ~10 dias.
- [ ] **Step 5:** Smoke aprovado → finishing-a-development-branch (merge no master).

---

## Riscos & notas pro executor

- **Task 1 é o GATE** — se o feed não servir JSON parseável, o probe redireciona (notificações) ou aborta. NÃO escreva Task 2+ contra shape imaginado; use a fixture real.
- **NUNCA IG real em teste** — núcleos `run_follows`/`detect_and_fetch`/`parse_*` são injetáveis; smokes são do usuário.
- **Seletores/URLs do IG são BRITTLE** (`?variant=following`, botão Seguir, og:image do post) — marcados "A CONFIRMAR no smoke"; o contrato estável são os parsers puros sobre JSON, no espírito do `instagram_source` existente.
- **Conta = burner antiga** (`.ig_session/`), não a @radarsp.noite. Follow é escrita: cap conservador no 1º ramp-up.
- **`ingest_ig` continua existindo** (vira semanal) — não delete; só sai do STEPS diário.
- **Windows:** `--basetemp=.pytest-tmp` em testes com tmp_path; `.ps1` com UTF-8 BOM.
