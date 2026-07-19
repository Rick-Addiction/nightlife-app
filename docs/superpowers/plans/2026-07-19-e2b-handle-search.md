# Ciclo E-2b: Descoberta de Handle via Busca no IG — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sob demanda, buscar o nome dos venues sem IG no Instagram (pela burner), confirmar o perfil certo em 2 passos, e anexar `venue.instagram` SÓ com match forte (o resto vira candidato auditável). Zero envenenamento automático.

**Architecture:** Spec `docs/superpowers/specs/2026-07-19-e2b-handle-search-design.md`. Reusa a plomberia Playwright da burner (captura JSON, não DOM) e as guardas anti-poison do Ciclo B. Peças: `ig_search.py` (parse_search_results puro + shells playwright_search/fetch_profile_signals), `handle_match.py` (shortlist + decide, PURO), `discover_ig_handles.py` (runner sob demanda). **Task 1 é um PROBE que captura o shape do JSON da busca — é o gate; o parser (Task 2) se ancora na fixture real.**

**Tech Stack:** Python 3.14 + Playwright (sync) + SQLAlchemy 2 + pytest. Sem dependência nova, sem migration (usa `venue.instagram` + `verification_logs`/`dedupe_candidates` existentes).

**Referências verificadas do código atual (2026-07-19, branch `feat/e2b-handle-search`):**
- `extraction/social.py`: `canonical_handle(raw) -> str|None` ('@Foo'/'instagram.com/foo/' → 'foo'; rejeita `_NON_PROFILE` [p/reel/explore/invites/share/locations] e inválidos); `handles_from_text`.
- `domain/nightlife_relevance.py`: `is_platform_handle(handle) -> bool` (sympla/ifood/instagram/whatsapp etc.).
- `domain/matching.py`: `name_similarity(a, b) -> float` (SequenceMatcher sobre `normalize_name`); `normalize_name`.
- `ingestion/instagram_source.py`: `open_context(user_data_dir, *, headful) -> (pw, context)` (persistent context da burner); `playwright_fetch_posts`/`playwright_fetch_feed` capturam JSON via `page.on("response")` — MESMO padrão pra busca/perfil.
- `persistence/ig_state.py`: `record_venue_activity`, `follow_queue`/`scrape_queue` (pegam venues com `instagram` — o handle anexado aqui alimenta o E-3 de graça).
- `models.py`: `Venue{instagram, website, category, confidence}`; `VerificationLog{entity_type, entity_id, note}`; `DedupeCandidate{kind, a_id, b_id, similarity_score, decision}`; `Event{venue_id, starts_at, status}`.
- `config.py`: `IG_USER_DATA_DIR` (`.ig_session`), `IG_HEADFUL`, `IG_DELAY_MIN/MAX` (4/11).
- Probe do feed (E-3): `src/nightlife/probe_feed.py` é o modelo do probe (captura JSON, salva fixture curada; `feed_source.py`/`watch_feed.py` são o padrão de shell+parser+runner).
- Testes: `.venv/Scripts/python -m pytest <arq> -v` (Postgres `docker compose up -d --wait`; suíte/tmp_path com `--basetemp=.pytest-tmp`, deletar; fixture `session`). **NUNCA IG real em teste.**

**Convenção de commit:** trailer `Claude-Session: b9eb4ce7-361b-434d-9809-31614b56e56d`. **Branch:** `feat/e2b-handle-search`. **Conta:** burner (`.ig_session/`).

---

### Task 1: PROBE da busca do IG (gate — captura o JSON real)

**Files:**
- Create: `src/nightlife/probe_ig_search.py`, `tests/fixtures/ig_search_sample.json` (curada)

Probe assistido (roda com o usuário, burner logada). Entrega: fixture do shape + veredito.

- [ ] **Step 1: Escrever o probe** (espelha `probe_feed.py`)

```python
# src/nightlife/probe_ig_search.py
"""PROBE (Ciclo E-2b, gate): busca um nome no IG e captura TODAS as respostas
JSON, salvando a que serve os resultados de usuario. Descobre o shape (onde
vem username/full_name/is_verified/follower_count). NAO roda em CI.
Uso: .venv/Scripts/python -m nightlife.probe_ig_search "Oficina Club"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import config
from .ingestion.instagram_source import open_context

OUT = Path("tests/fixtures")


def _keys(d, depth=0):
    if depth > 4 or not isinstance(d, dict):
        return
    for k, v in d.items():
        yield k
        if isinstance(v, dict):
            yield from _keys(v, depth + 1)


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "Oficina Club"
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
        # UI de busca: abre a home, foca a busca e digita (a URL/endpoint exatos
        # o probe revela). Alternativa: topsearch endpoint direto.
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        # dispara a busca via UI se houver caixa; senao, o usuario digita manualmente
        try:
            page.get_by_role("link", name="Pesquisa").click(timeout=5000)
            page.wait_for_timeout(1000)
            box = page.get_by_role("textbox").first
            box.fill(query)
            page.wait_for_timeout(4000)
        except Exception:  # noqa: BLE001 — UI mudou; usuario digita na janela headful
            print("nao achei a caixa de busca — digite manualmente na janela e aguarde.")
            page.wait_for_timeout(15000)
        page.close()
    finally:
        context.close()
        pw.stop()

    hits = [d for d in captured
            if any(k for k in _keys(d) if k in ("users", "user", "num_results") or "search" in k.lower())]
    (OUT / "ig_search_probe_raw.json").write_text(
        json.dumps(hits[:5], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"capturei {len(captured)} respostas JSON; {len(hits)} com cara de busca.")
    print(f"salvo em {OUT / 'ig_search_probe_raw.json'} — inspecione o shape.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Rodar COM O USUÁRIO** (burner logada, headful):
`.venv/Scripts/python -m nightlife.probe_ig_search "Oficina Club"`
Inspecionar `ig_search_probe_raw.json`. Identificar: onde vem a lista de usuários (provável `users[].user{username, full_name, is_verified, follower_count}` do endpoint `topsearch`) e a chave da lista.

- [ ] **Step 3: Fixture curada** — extrair 2-3 resultados reais → `tests/fixtures/ig_search_sample.json` (a lista + campos que o parser consome; inclua um verificado e um não-verificado). NÃO commitar o `_raw`.

- [ ] **Step 4: VEREDITO (gate)** — busca serve JSON parseável → segue Task 2+. Senão → replaneja (DOM) ou aborta e reporta ao usuário.

- [ ] **Step 5: Commit** `feat: probe da busca do IG (gate E-2b) + fixture do shape real`

---

### Task 2: `parse_search_results` (puro, ancorado na fixture)

**Files:**
- Create: `src/nightlife/ingestion/ig_search.py`
- Test: `tests/test_ig_search.py`

**PRÉ:** Task 1 concluída; `tests/fixtures/ig_search_sample.json` existe e você conhece a chave da lista e os paths. Os literais abaixo assumem o shape provável do `topsearch` (`users[].user.{username,full_name,is_verified,follower_count}`); **ajuste ao que o probe achou** — a fixture é a fonte da verdade.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ig_search.py
import json
from pathlib import Path
from nightlife.ingestion.ig_search import SearchResult, parse_search_results

FIXTURE = json.loads(Path("tests/fixtures/ig_search_sample.json").read_text(encoding="utf-8"))


def test_parse_search_results_extrai_campos():
    rs = parse_search_results(FIXTURE)
    assert len(rs) >= 2
    r = rs[0]
    assert isinstance(r, SearchResult)
    assert r.username
    assert isinstance(r.is_verified, bool)
    assert r.follower_count is None or isinstance(r.follower_count, int)


def test_parse_search_results_json_sem_users_vazio():
    assert parse_search_results({"data": {"outra": 1}}) == []
```

- [ ] **Step 2: Run** → FAIL (módulo não existe). **Step 3: Implement** (ajuste `_USERS_PATH` ao probe):

```python
# src/nightlife/ingestion/ig_search.py
"""Busca no IG como fonte de handle (Ciclo E-2b). parse_search_results PURO
(fixture do probe); playwright_search/fetch_profile_signals sao shells smoke."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SearchResult:
    username: str
    full_name: str | None
    is_verified: bool
    follower_count: int | None


def _user_nodes(graphql: dict) -> list:
    # CONFIRMAR no probe: topsearch serve 'users' na raiz; cada item tem 'user'.
    users = graphql.get("users")
    if isinstance(users, list):
        return users
    return []


def parse_search_results(graphql: dict) -> list[SearchResult]:
    out: list[SearchResult] = []
    for node in _user_nodes(graphql):
        u = node.get("user") if isinstance(node.get("user"), dict) else node
        username = (u or {}).get("username")
        if not username:
            continue
        out.append(SearchResult(
            username=username,
            full_name=(u.get("full_name") or None),
            is_verified=bool(u.get("is_verified")),
            follower_count=(u.get("follower_count") if isinstance(u.get("follower_count"), int) else None),
        ))
    return out
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat(ig): parse_search_results — extrai username/verificado/seguidores da busca`

---

### Task 3: Matching + decisão (`handle_match.py`, puro)

**Files:**
- Create: `src/nightlife/ingestion/handle_match.py`
- Test: `tests/test_handle_match.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_handle_match.py
from nightlife.ingestion.ig_search import SearchResult
from nightlife.ingestion.handle_match import (
    ProfileSignals, decide, norm_url, shortlist, NAME_FLOOR,
)


def _r(u, name, ver=False, fol=1000):
    return SearchResult(username=u, full_name=name, is_verified=ver, follower_count=fol)


def test_norm_url_tira_scheme_www_barra():
    assert norm_url("https://www.selva.club/") == "selva.club"
    assert norm_url("http://selva.club") == "selva.club"
    assert norm_url(None) is None


def test_shortlist_filtra_por_similaridade_e_ordena():
    rs = [_r("selvaclub", "Selva Club", fol=5000), _r("outrolugar", "Outro Bar", fol=99999),
          _r("selva.011", "Selva Club SP", fol=8000)]
    sl = shortlist("Selva Club", rs)
    assert all(s.username != "outrolugar" for s in sl)   # nome nao bate -> fora
    assert sl                                             # os "Selva" entram
    assert NAME_FLOOR >= 0.5


def _sig(handle, link=None, cat=None, bio="", ver=False, fol=1000):
    return ProfileSignals(handle=handle, bio_link=link, category=cat, bio_text=bio,
                          is_verified=ver, follower_count=fol)


def test_decide_attach_por_bio_link_igual_ao_site():
    d = decide(venue_name="Selva Club", venue_website="https://selva.club/", venue_neighborhood="Consolação",
               best=_r("selva.011", "Selva Club", ver=False),
               signals=_sig("selva.011", link="https://selva.club"))
    assert d.action == "attach" and d.handle == "selva.011"
    assert "site" in d.reason.lower()


def test_decide_attach_por_verificado_e_nome_forte():
    d = decide(venue_name="D-Edge", venue_website=None, venue_neighborhood="Barra Funda",
               best=_r("dedgeclub", "D-Edge", ver=True, fol=200000),
               signals=_sig("dedgeclub", cat="Night Club", ver=True, fol=200000))
    assert d.action == "attach"


def test_decide_review_sem_confirmador_forte():
    d = decide(venue_name="Manifesto Bar", venue_website=None, venue_neighborhood=None,
               best=_r("manifestobar", "Manifesto Bar", ver=False, fol=1200),
               signals=_sig("manifestobar", cat=None, bio="", ver=False, fol=1200))
    assert d.action == "review"


def test_decide_reject_platform_handle():
    d = decide(venue_name="X", venue_website=None, venue_neighborhood=None,
               best=_r("sympla", "Sympla", ver=True),
               signals=_sig("sympla", ver=True))
    assert d.action == "reject"
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**

```python
# src/nightlife/ingestion/handle_match.py
"""Decide se um resultado de busca e MESMO o venue (Ciclo E-2b). PURO. Anti-
envenenamento (fantasma do Ciclo B): so 'attach' com confirmador FORTE; resto
'review'; platform/handle invalido 'reject'."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from ..domain.matching import name_similarity
from ..domain.nightlife_relevance import is_platform_handle
from ..extraction.social import canonical_handle
from .ig_search import SearchResult

NAME_FLOOR = 0.6          # piso de similaridade pro shortlist
_STRONG_NAME = 0.8        # nome "muito forte" (attach por verificado)
_NIGHTLIFE_CATS = ("night club", "bar", "dance", "music venue", "casa noturna", "boate")


@dataclass
class ProfileSignals:
    handle: str
    bio_link: str | None
    category: str | None
    bio_text: str
    is_verified: bool
    follower_count: int | None


@dataclass
class MatchDecision:
    action: str          # "attach" | "review" | "reject"
    handle: str | None
    reason: str


def norm_url(u: str | None) -> str | None:
    if not u:
        return None
    s = u.strip().lower()
    for p in ("https://", "http://"):
        if s.startswith(p):
            s = s[len(p):]
    if s.startswith("www."):
        s = s[4:]
    return s.rstrip("/") or None


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower())
                   if unicodedata.category(c) != "Mn")


def shortlist(venue_name: str, results: list[SearchResult]) -> list[SearchResult]:
    scored = [(name_similarity(venue_name, r.full_name or r.username), r) for r in results]
    keep = [(sc, r) for sc, r in scored if sc >= NAME_FLOOR]
    keep.sort(key=lambda t: (t[0], t[1].follower_count or 0), reverse=True)
    return [r for _, r in keep]


def decide(*, venue_name: str, venue_website: str | None, venue_neighborhood: str | None,
           best: SearchResult, signals: ProfileSignals) -> MatchDecision:
    handle = canonical_handle(best.username)
    if not handle or is_platform_handle(handle):
        return MatchDecision("reject", None, "platform/handle invalido")
    sim = name_similarity(venue_name, best.full_name or best.username)

    # confirmador DEFINITIVO: link-na-bio == site do venue (elo E-2a)
    if venue_website and signals.bio_link and norm_url(signals.bio_link) == norm_url(venue_website):
        return MatchDecision("attach", handle, f"bio_link == site do venue ({norm_url(venue_website)})")

    # verificado + nome muito forte
    if signals.is_verified and sim >= _STRONG_NAME:
        return MatchDecision("attach", handle, f"verificado + nome forte (sim={sim:.2f})")

    # categoria nightlife + bio menciona o bairro/SP
    cat = _norm(signals.category or "")
    bio = _norm(signals.bio_text)
    is_nightlife = any(w in cat for w in _NIGHTLIFE_CATS)
    place_hit = ("sao paulo" in bio or "sp" in bio.split()
                 or (venue_neighborhood and _norm(venue_neighborhood) in bio))
    if is_nightlife and place_hit and sim >= _STRONG_NAME:
        return MatchDecision("attach", handle, f"nightlife + local na bio (sim={sim:.2f})")

    return MatchDecision("review", handle, f"sem confirmador forte (sim={sim:.2f}, ver={signals.is_verified})")
```

- [ ] **Step 4: Run** `.venv/Scripts/python -m pytest tests/test_handle_match.py -v` → PASS. **Step 5: Commit** `feat(ig): handle_match — shortlist + decide (attach forte/review/reject) anti-poison`

---

### Task 4: Shells de busca e perfil (`ig_search.py`)

**Files:**
- Modify: `src/nightlife/ingestion/ig_search.py` (acrescentar shells)
- Test: nenhum (shells smoke-calibrados; verificar import)

- [ ] **Step 1: Implement** (no fim de `ig_search.py`; espelha `playwright_fetch_feed`):

```python
from pathlib import Path  # topo do arquivo


def playwright_search(context, query: str) -> list[SearchResult]:
    """Dispara a busca no IG e captura o JSON; parse_search_results extrai.
    BRITTLE (o IG muda): URL/UI calibradas no probe/smoke."""
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
    try:
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        page.get_by_role("link", name="Pesquisa").click(timeout=8000)
        page.wait_for_timeout(1000)
        box = page.get_by_role("textbox").first
        box.fill(query)
        page.wait_for_timeout(4000)
    finally:
        page.close()
    for data in captured:
        rs = parse_search_results(data)
        if rs:
            return rs
    return []


def fetch_profile_signals(context, handle: str) -> "ProfileSignals":
    """Abre o perfil e extrai sinais de confirmacao (bio_link/category/bio/verificado).
    Reusa a captura de JSON do perfil; seletores calibrados no smoke."""
    from .handle_match import ProfileSignals
    page = context.new_page()
    info: dict = {}

    def _on_response(resp):
        if "application/json" not in resp.headers.get("content-type", ""):
            return
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return
        # CONFIRMAR no smoke: o perfil serve o user em data.user ou
        # data.data.user com external_url/category/biography/is_verified.
        u = ((data.get("data") or {}).get("user")) or data.get("user")
        if isinstance(u, dict) and u.get("username"):
            info.update(u)

    page.on("response", _on_response)
    try:
        page.goto(f"https://www.instagram.com/{handle}/", wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(2500)
    finally:
        page.close()
    fol = info.get("edge_followed_by") or {}
    return ProfileSignals(
        handle=handle,
        bio_link=info.get("external_url"),
        category=info.get("category_name") or info.get("category"),
        bio_text=info.get("biography") or "",
        is_verified=bool(info.get("is_verified")),
        follower_count=(fol.get("count") if isinstance(fol, dict) else info.get("follower_count")),
    )
```

- [ ] **Step 2: Verify** `.venv/Scripts/python -c "import nightlife.ingestion.ig_search"` → ok; `tests/test_ig_search.py` verde. **Step 3: Commit** `feat(ig): shells playwright_search + fetch_profile_signals (smoke-calibrados)`

---

### Task 5: Runner `discover_ig_handles`

**Files:**
- Create: `src/nightlife/discover_ig_handles.py`
- Test: `tests/test_discover_ig_handles.py`

- [ ] **Step 1: Write the failing tests** (núcleo `discover` injetável)

```python
# tests/test_discover_ig_handles.py
from datetime import datetime, timezone
from nightlife.discover_ig_handles import discover, no_ig_venues
from nightlife.ingestion.ig_search import SearchResult
from nightlife.ingestion.handle_match import ProfileSignals
from nightlife.models import Event, VerificationLog, Venue


def test_no_ig_venues_futuros_primeiro(session):
    a = Venue(name="ComFuturo", category="nightclub", lat=-23.55, lng=-46.65, confidence=50)
    b = Venue(name="SemFuturo", category="nightclub", lat=-23.55, lng=-46.65, confidence=50)
    tem_ig = Venue(name="TemIG", category="nightclub", instagram="x", lat=-23.55, lng=-46.65, confidence=50)
    session.add_all([a, b, tem_ig]); session.flush()
    session.add(Event(name="F", status="scheduled", confidence=50, venue_id=a.id,
                      starts_at=datetime(2099, 1, 1, tzinfo=timezone.utc)))
    session.flush()
    vs = no_ig_venues(session)
    assert tem_ig.id not in {v.id for v in vs}      # ja tem IG -> fora
    assert vs[0].id == a.id                         # com futuro primeiro


def test_discover_attach_seta_instagram_e_loga(session):
    v = Venue(name="Selva Club", website="https://selva.club/", category="nightclub",
              lat=-23.55, lng=-46.65, confidence=50)
    session.add(v); session.flush()

    def fake_search(ctx, q):
        return [SearchResult("selva.011", "Selva Club", is_verified=False, follower_count=9000)]
    def fake_profile(ctx, h):
        return ProfileSignals(h, bio_link="https://selva.club", category="Night Club",
                              bio_text="Consolação SP", is_verified=False, follower_count=9000)

    stats = discover(session, [v], context=None, search=fake_search,
                     profile=fake_profile, delay=lambda: None)
    assert v.instagram == "selva.011"
    assert stats["attach"] == 1
    assert session.query(VerificationLog).filter(VerificationLog.note.ilike("%ig_search%")).count() == 1


def test_discover_review_nao_anexa(session):
    v = Venue(name="Manifesto Bar", category="nightclub", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v); session.flush()
    def fake_search(ctx, q):
        return [SearchResult("manifestobar", "Manifesto Bar", is_verified=False, follower_count=800)]
    def fake_profile(ctx, h):
        return ProfileSignals(h, bio_link=None, category=None, bio_text="", is_verified=False, follower_count=800)
    stats = discover(session, [v], context=None, search=fake_search,
                     profile=fake_profile, delay=lambda: None)
    assert v.instagram is None                       # nao anexou
    assert stats["review"] == 1


def test_discover_sem_resultado_nao_quebra(session):
    v = Venue(name="Fantasma", category="nightclub", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v); session.flush()
    stats = discover(session, [v], context=None, search=lambda c, q: [],
                     profile=lambda c, h: None, delay=lambda: None)
    assert v.instagram is None and stats["review"] == 0 and stats["attach"] == 0
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**

```python
# src/nightlife/discover_ig_handles.py
"""Descobre handle de IG dos venues sem instagram via busca (Ciclo E-2b).
Sob demanda. Uso: .venv/Scripts/python -m nightlife.discover_ig_handles [--limit N]"""
from __future__ import annotations

import argparse
import random
import time
from typing import Callable

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from . import config
from .db import SessionLocal
from .ingestion.handle_match import decide, shortlist
from .models import Event, VerificationLog, Venue


def no_ig_venues(session: Session) -> list[Venue]:
    """Venues nightclub sem instagram, FUTUROS-primeiro (evento futuro), depois resto."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    fut = set(session.scalars(
        select(Event.venue_id).where(Event.venue_id.is_not(None), Event.starts_at > now)).all())
    vs = list(session.scalars(
        select(Venue).where(Venue.instagram.is_(None), Venue.category == "nightclub")
        .order_by(Venue.confidence.desc())))
    vs.sort(key=lambda v: v.id not in fut)     # False(0)=futuro primeiro
    return vs


def discover(session: Session, venues: list[Venue], *, context,
             search: Callable, profile: Callable, delay: Callable[[], None]) -> dict:
    stats = {"attach": 0, "review": 0, "reject": 0}
    for v in venues:
        try:
            results = search(context, v.name)
            sl = shortlist(v.name, results)
            if not sl:
                continue
            best = sl[0]
            signals = profile(context, best.username)
            if signals is None:
                continue
            d = decide(venue_name=v.name, venue_website=v.website,
                       venue_neighborhood=None, best=best, signals=signals)
            if d.action == "attach":
                v.instagram = d.handle
                session.add(VerificationLog(entity_type="venue", entity_id=v.id,
                            note=f"handle via ig_search: @{d.handle} — {d.reason}"))
                stats["attach"] += 1
            elif d.action == "review":
                session.add(VerificationLog(entity_type="venue", entity_id=v.id,
                            note=f"ig_search review: candidato @{d.handle} — {d.reason}"))
                stats["review"] += 1
            else:
                stats["reject"] += 1
        except Exception as exc:  # noqa: BLE001 — falha isolada por venue
            print(f"  {v.name[:30]}: erro {str(exc)[:60]}")
        session.commit()
        delay()
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    from .ingestion.instagram_source import open_context
    from .ingestion.ig_search import fetch_profile_signals, playwright_search
    with SessionLocal() as session:
        venues = no_ig_venues(session)
        if args.limit:
            venues = venues[: args.limit]
        if not venues:
            print("nenhum venue sem IG.")
            return
        pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
        try:
            stats = discover(session, venues, context=context,
                             search=playwright_search, profile=fetch_profile_signals,
                             delay=lambda: time.sleep(random.uniform(config.IG_DELAY_MIN,
                                                                     config.IG_DELAY_MAX)))
        finally:
            context.close(); pw.stop()
        print(f"handles: attach={stats['attach']} review={stats['review']} reject={stats['reject']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run** `.venv/Scripts/python -m pytest tests/test_discover_ig_handles.py -v --basetemp=.pytest-tmp` → PASS (delete). Import: `.venv/Scripts/python -c "import nightlife.discover_ig_handles"`. **Step 5: Commit** `feat(ig): discover_ig_handles runner — busca->confirma->attach/review por venue`

---

### Task 6: Final — suíte + smoke real (assistido)

- [ ] **Step 1:** `.venv/Scripts/python -m pytest -q --basetemp=.pytest-tmp` (delete depois) → verde.
- [ ] **Step 2 (smoke assistido — burner logada):** `.venv/Scripts/python -m nightlife.discover_ig_handles --limit 5` (começa pelos futuros; se o Oficina Club estiver sem IG, ele deve entrar). Conferir: attaches corretos (`venue.instagram` setado nos certos, com log do motivo), e o que foi pra review no `verification_logs`. **Confirmar os débitos de shell** (URL/caixa de busca do `playwright_search`, paths do perfil em `fetch_profile_signals`) — ajustar seletores se a busca vier vazia ou o perfil sem sinais.
- [ ] **Step 3 (smoke do usuário):** revisar no SQL os attaches (`SELECT name, instagram FROM venues WHERE instagram IS NOT NULL AND ...`) e os reviews — validar que nenhum handle errado foi anexado (anti-poison).
- [ ] **Step 4:** Smoke aprovado → finishing-a-development-branch (merge no master).

---

## Riscos & notas pro executor

- **Task 1 é o GATE** — se a busca não servir JSON parseável, replaneja/aborta; use a fixture real, não shape imaginado.
- **NUNCA IG real em teste** — `parse_search_results`/`shortlist`/`decide`/`discover` são puros/injetáveis; shells (`playwright_search`/`fetch_profile_signals`) são smoke.
- **Anti-envenenamento é o ponto**: `decide` só faz `attach` com confirmador FORTE; qualquer dúvida → `review`. Guardas `canonical_handle`/`is_platform_handle` reusadas.
- **Seletores/endpoints do IG brittle** (`?variant`, caixa de busca, paths do perfil) — marcados "a confirmar no smoke"; contrato estável são os parsers puros sobre JSON.
- **Conta = burner** (`.ig_session/`); busca é leitura (mais leve que follow), mas `--limit` + delays.
- **Windows**: `--basetemp=.pytest-tmp` em testes com DB/tmp_path.
- **Sinergia**: handle anexado → o venue entra na fila do E-3 (`follow_queue`/`scrape_queue`) automaticamente. Nada a fazer.
