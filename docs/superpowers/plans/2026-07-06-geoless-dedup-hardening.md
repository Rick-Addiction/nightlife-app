# Endurecer o dedup geoless — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Impedir merges falsos de venues sem geo (candidato geoless → nunca `auto_merge`) sem quebrar a idempotência (identidade por `source_url`), e limpar os 14 colapsos já no banco.

**Architecture:** Spec: `docs/superpowers/specs/2026-07-06-geoless-dedup-hardening-design.md`. Duas peças no core: **3A** `classify_venue_match` (sem geo → `review`/`distinct`); **3B** `upsert_venue` reconhece o MESMO venue por `(source_type, source_url)` antes do matching por nome (idempotência independente de geo). + runner `repair_ra_dedup` que apaga só dados `source_type="ra"` (re-derivável).

**Tech Stack:** Python 3.14, SQLAlchemy 2.0, pytest. Postgres (Docker 5434).

**Convenções:**
- **cwd do shell RESETA entre chamadas Bash** — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Python: `.venv/Scripts/python`. Testes: `.venv/Scripts/python -m pytest ... --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife` (SEMPRE; confie no exit code — a linha "N passed" some no pipe).
- Suíte backend hoje = **161**. Commits com trailer `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`. **NÃO** mexa em `web/`.

---

## File Structure

```
src/nightlife/domain/matching.py        # MODIFICA — classify_venue_match (3A)
src/nightlife/persistence/venues_repo.py# MODIFICA — upsert_venue identidade por source_url (3B)
src/nightlife/repair_ra_dedup.py        # NOVO — runner de limpeza
tests/test_matching.py                  # MODIFICA
tests/test_venues_repo.py               # MODIFICA
tests/test_repair_ra_dedup.py           # NOVO
```

## Contexto de código (já existe)

- `domain/matching.py`: `classify_venue_match(score, *, distance_km=None)`, `VENUE_MERGE_THRESHOLD=0.85`, `VENUE_REVIEW_THRESHOLD=0.70`, `MAX_DUPLICATE_DISTANCE_KM=1.0`, `match_venue`, `geo_distance_km`, `VenueRef`.
- `persistence/venues_repo.py`: `upsert_venue(session, candidate, source, *, reference)` — hoje: `match_venue` → `classify_venue_match` → auto_merge (reusa venue) / review (cria + DedupeCandidate) / distinct (cria). Imports: `from ..models import DedupeCandidate, Venue`; `from .confidence import VENUE_SOURCE_CONTRIBUTION, recompute_venue_confidence`; `from .evidence import record_venue_evidence`; `select` de sqlalchemy; `datetime, timezone`.
- `models.py`: `Venue` (rel `sources`, `events`), `VenueSource` (venue_id, source_type, source_url), `Event` (rel `sources`, venue_id), `EventSource` (event_id, source_type, source_url), `DedupeCandidate`.

---

## Task 1: `classify_venue_match` — sem geo nunca funde (3A)

**Files:** Modify `src/nightlife/domain/matching.py`; Modify `tests/test_matching.py`

- [ ] **Step 1: Atualizar/adicionar testes** — em `tests/test_matching.py`:

(a) SUBSTITUA `test_classify_venue_match_bands` por (as faixas valem COM geo confirmado):
```python
def test_classify_venue_match_bands():
    from nightlife.domain.matching import classify_venue_match
    # as faixas de merge/review/distinct valem COM geo (perto)
    assert classify_venue_match(0.90, distance_km=0.3) == "auto_merge"
    assert classify_venue_match(0.85, distance_km=0.3) == "auto_merge"
    assert classify_venue_match(0.78, distance_km=0.3) == "review"
    assert classify_venue_match(0.70, distance_km=0.3) == "review"
    assert classify_venue_match(0.60, distance_km=0.3) == "distinct"
```

(b) ADICIONE ao final:
```python
def test_classify_geoless_nunca_auto_merge():
    from nightlife.domain.matching import classify_venue_match
    # sem geo (distance_km=None) NAO da pra confirmar o lugar -> nunca auto_merge
    assert classify_venue_match(1.0, distance_km=None) == "review"
    assert classify_venue_match(0.90, distance_km=None) == "review"
    assert classify_venue_match(0.70, distance_km=None) == "review"
    assert classify_venue_match(0.60, distance_km=None) == "distinct"
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_matching.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `test_classify_geoless_nunca_auto_merge` (hoje `classify(1.0, None)` → "auto_merge", não "review").

- [ ] **Step 3: Implementar** — em `src/nightlife/domain/matching.py`, SUBSTITUA o corpo de `classify_venue_match` por:
```python
def classify_venue_match(score: float, *, distance_km: float | None = None) -> str:
    """Faixas de decisao para upsert de venue: merge automatico so em alta
    confianca E com geo que confirme o lugar fisico. Sem geo (distance_km=None)
    nao da pra distinguir 'Mono Club' de 'Club Mono' -> nunca auto_merge."""
    if distance_km is not None and distance_km > MAX_DUPLICATE_DISTANCE_KM:
        return "distinct"                 # longe demais = lugares diferentes
    if distance_km is None:               # sem geo: sem confirmacao fisica
        return "review" if score >= VENUE_REVIEW_THRESHOLD else "distinct"
    if score >= VENUE_MERGE_THRESHOLD:
        return "auto_merge"
    if score >= VENUE_REVIEW_THRESHOLD:
        return "review"
    return "distinct"
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_matching.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (todos).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/domain/matching.py tests/test_matching.py && git commit -m "fix(dedup): classify_venue_match — sem geo nunca auto_merge (review/distinct)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: `upsert_venue` — identidade por source_url (3B)

**Files:** Modify `src/nightlife/persistence/venues_repo.py`; Modify `tests/test_venues_repo.py`

**Por que:** com a Task 1, um venue geoless re-ingerido cairia em `review` e duplicaria a cada run. A identidade por `source_url` reconhece o MESMO venue (idempotente) antes do matching por nome.

- [ ] **Step 1: Teste que falha** — em `tests/test_venues_repo.py`, ADICIONE ao final:
```python
def test_geoless_mesmo_source_url_e_idempotente(session):
    # venue SEM geo, re-ingerido com o MESMO (source_type, source_url) -> 1 venue
    upsert_venue(session, VenueInput(name="D-EDGE"), _src("ra", "https://ra.co/clubs/4973"), reference=REF)
    upsert_venue(session, VenueInput(name="D-EDGE"), _src("ra", "https://ra.co/clubs/4973"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 1
    assert len(session.scalars(select(VenueSource)).all()) == 1


def test_geoless_nomes_iguais_fontes_diferentes_viram_review(session):
    # "Club Mono" e "Mono Club" normalizam p/ "mono" (score 1.0), mas SEM geo e de
    # fontes diferentes -> review (cria 2o venue), NUNCA funde
    upsert_venue(session, VenueInput(name="Club Mono"), _src("ra", "https://ra.co/clubs/1"), reference=REF)
    upsert_venue(session, VenueInput(name="Mono Club"), _src("osm", "https://osm.org/9"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 2          # nao fundiu
    cands = session.scalars(select(DedupeCandidate)).all()
    assert len(cands) == 1 and cands[0].decision == "review"
```
E garanta o import de `VenueSource` no topo do arquivo de teste (junto de `DedupeCandidate, Venue`):
```python
from nightlife.models import DedupeCandidate, Venue, VenueSource
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_venues_repo.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `test_geoless_mesmo_source_url_e_idempotente` (após a Task 1, o 2º upsert geoless vira review → cria 2º venue → 2 venues, não 1).

- [ ] **Step 3: Implementar** — em `src/nightlife/persistence/venues_repo.py`:

Adicione `VenueSource` ao import de models:
```python
from ..models import DedupeCandidate, Venue, VenueSource
```

SUBSTITUA a função `upsert_venue` inteira por (extrai `_fill_and_record` p/ DRY + adiciona a identidade por source_url no início):
```python
def _fill_and_record(session: Session, venue: Venue, candidate: VenueInput,
                     source: SourceInfo, reference: date) -> Venue:
    """Reusa um venue existente: preenche lacunas, grava evidencia (idempotente),
    recomputa confianca."""
    venue.last_seen_at = datetime.now(timezone.utc)
    venue.lat = venue.lat if venue.lat is not None else candidate.lat
    venue.lng = venue.lng if venue.lng is not None else candidate.lng
    venue.address = venue.address or candidate.address
    venue.category = venue.category or candidate.category
    record_venue_evidence(
        session, venue.id, source,
        contribution=VENUE_SOURCE_CONTRIBUTION.get(source.source_type, 0),
    )
    recompute_venue_confidence(session, venue, reference=reference)
    return venue


def upsert_venue(
    session: Session, candidate: VenueInput, source: SourceInfo, *, reference: date
) -> Venue:
    # identidade por source_url: mesmo (source_type, source_url) = MESMA venue,
    # idempotente e independente de geo (senao venue sem geo duplicaria a cada run).
    if source.source_url:
        known = session.scalars(
            select(Venue).join(VenueSource).where(
                VenueSource.source_type == source.source_type,
                VenueSource.source_url == source.source_url,
            )
        ).first()
        if known is not None:
            return _fill_and_record(session, known, candidate, source, reference)

    existing = session.scalars(select(Venue)).all()
    refs = [VenueRef(v.id, v.name, v.address, v.lat, v.lng) for v in existing]
    cand_ref = VenueRef(None, candidate.name, candidate.address, candidate.lat, candidate.lng)
    best = match_venue(cand_ref, refs, threshold=0.0)
    decision = "distinct"
    if best is not None:
        decision = classify_venue_match(
            best.score, distance_km=geo_distance_km(cand_ref, best.venue)
        )

    if decision == "auto_merge":
        return _fill_and_record(session, session.get(Venue, best.venue.id), candidate, source, reference)

    venue = Venue(
        name=candidate.name, lat=candidate.lat, lng=candidate.lng,
        address=candidate.address, category=candidate.category, status="unverified",
    )
    session.add(venue)
    session.flush()
    if decision == "review":
        session.add(DedupeCandidate(
            kind="venue", a_id=venue.id, b_id=best.venue.id,
            similarity_score=best.score, decision="review",
        ))
    record_venue_evidence(
        session, venue.id, source,
        contribution=VENUE_SOURCE_CONTRIBUTION.get(source.source_type, 0),
    )
    recompute_venue_confidence(session, venue, reference=reference)
    return venue
```

- [ ] **Step 4: Ver passar + commit** — inclui os testes existentes (idempotência/auto_merge não podem regredir):

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_venues_repo.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (todos — incl. `test_rerun_same_source_is_idempotent`, que agora passa VIA a identidade por source_url, e `test_auto_merge_accumulates_confidence`, inalterado).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/persistence/venues_repo.py tests/test_venues_repo.py && git commit -m "fix(dedup): upsert_venue identidade por source_url (idempotencia geoless)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: Runner `repair_ra_dedup` (limpa os 14 colapsos)

**Files:** Create `src/nightlife/repair_ra_dedup.py`; Create `tests/test_repair_ra_dedup.py`

- [ ] **Step 1: Teste que falha** — crie `tests/test_repair_ra_dedup.py`:
```python
from sqlalchemy import select

from nightlife.models import DedupeCandidate, Event, EventSource, Venue, VenueSource
from nightlife.repair_ra_dedup import repair


def test_repair_apaga_so_dados_ra(session):
    # venue OSM que absorveu evidencia RA falsa (sobrevive, perde a evidencia RA)
    osm = Venue(name="Mono Club", lat=-23.5, lng=-46.6)
    session.add(osm); session.flush()
    session.add_all([
        VenueSource(venue_id=osm.id, source_type="osm", source_url="https://osm.org/1"),
        VenueSource(venue_id=osm.id, source_type="ra", source_url="https://ra.co/clubs/1"),
    ])
    # venue RA-only orfao (some)
    ra_only = Venue(name="D-EDGE")
    session.add(ra_only); session.flush()
    session.add(VenueSource(venue_id=ra_only.id, source_type="ra", source_url="https://ra.co/clubs/2"))
    # evento RA-only (some)
    ev_ra = Event(name="Festa RA", status="scheduled")
    session.add(ev_ra); session.flush()
    session.add(EventSource(event_id=ev_ra.id, source_type="ra", source_url="https://ra.co/events/1"))
    # evento multi-fonte (sobrevive, perde a evidencia RA)
    ev_multi = Event(name="Festa Multi", status="scheduled")
    session.add(ev_multi); session.flush()
    session.add_all([
        EventSource(event_id=ev_multi.id, source_type="ra", source_url="https://ra.co/events/2"),
        EventSource(event_id=ev_multi.id, source_type="ticketing", source_url="https://sympla/9"),
    ])
    session.flush()

    repair(session)
    session.flush()

    assert session.get(Venue, osm.id) is not None                     # OSM sobrevive
    assert [s.source_type for s in session.scalars(
        select(VenueSource).where(VenueSource.venue_id == osm.id)).all()] == ["osm"]
    assert session.get(Venue, ra_only.id) is None                     # RA-only some
    assert session.get(Event, ev_ra.id) is None                       # evento RA-only some
    assert session.get(Event, ev_multi.id) is not None                # multi-fonte sobrevive
    assert [s.source_type for s in session.scalars(
        select(EventSource).where(EventSource.event_id == ev_multi.id)).all()] == ["ticketing"]
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_repair_ra_dedup.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar** — crie `src/nightlife/repair_ra_dedup.py`:
```python
# src/nightlife/repair_ra_dedup.py
"""Repara os merges falsos geoless do RA: apaga SO os dados source_type='ra'
(re-derivaveis), deixando OSM/Sympla/flyer intactos. Depois rode ingest_ra p/
re-criar os venues do RA ja com o dedup endurecido (separados, sem colapso).

Uso: .venv/Scripts/python -m nightlife.repair_ra_dedup  (depois: -m nightlife.ingest_ra)
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import DedupeCandidate, Event, EventSource, Venue, VenueSource


def repair(session: Session) -> dict:
    """Apaga evidencia/venues/eventos que sao SO do RA. Retorna contagens.
    Ordem FK-safe: evidencia RA -> eventos orfaos -> evidencia RA -> venues orfaos."""
    ev_srcs = session.scalars(select(EventSource).where(EventSource.source_type == "ra")).all()
    for s in ev_srcs:
        session.delete(s)
    session.flush()

    orphan_events = session.scalars(select(Event).where(~Event.sources.any())).all()
    for e in orphan_events:
        session.delete(e)
    session.flush()

    v_srcs = session.scalars(select(VenueSource).where(VenueSource.source_type == "ra")).all()
    for s in v_srcs:
        session.delete(s)
    session.flush()

    orphan_venues = session.scalars(
        select(Venue).where(~Venue.sources.any(), ~Venue.events.any())
    ).all()
    for v in orphan_venues:
        session.delete(v)
    session.flush()

    cands = session.scalars(select(DedupeCandidate)).all()
    for c in cands:
        session.delete(c)
    session.flush()

    return {"event_sources_ra": len(ev_srcs), "eventos_orfaos": len(orphan_events),
            "venue_sources_ra": len(v_srcs), "venues_orfaos": len(orphan_venues),
            "dedupe_candidates": len(cands)}


def main() -> None:
    with SessionLocal() as session:
        counts = repair(session)
        session.commit()
        print("repair RA:", counts)
        print("agora rode: .venv/Scripts/python -m nightlife.ingest_ra")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_repair_ra_dedup.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (1).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/repair_ra_dedup.py tests/test_repair_ra_dedup.py && git commit -m "feat(dedup): runner repair_ra_dedup — apaga so dados RA (re-derivavel)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 4: Suíte + reparo real + smoke

**Files:** nenhum de produção novo.

- [ ] **Step 1: Suíte inteira verde**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife -p no:cacheprovider; echo "exit: $?"`
Expected: `exit: 0` (161 + 4 novos = 165).

- [ ] **Step 2: Reparar o banco real + re-ingerir o RA com o fix**

Run:
```bash
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m nightlife.repair_ra_dedup && .venv/Scripts/python -m nightlife.ingest_ra
```
Expected: o repair imprime as contagens do que apagou; o `ingest_ra` re-cria os venues do RA (agora separados). Cole a saída.

- [ ] **Step 3: Confirmar que os colapsos sumiram e a idempotência vale**

Run:
```bash
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -c "
from nightlife.db import SessionLocal
from nightlife.models import Venue, VenueSource
from sqlalchemy import select, func
with SessionLocal() as s:
    # nenhum venue deve ter 2+ evidencias RA distintas (o sinal de colapso)
    from collections import Counter
    ra = s.scalars(select(VenueSource).where(VenueSource.source_type=='ra')).all()
    per_venue = Counter(x.venue_id for x in ra)
    colapsos = [vid for vid,n in per_venue.items() if n >= 2]
    print('venues com 2+ evidencias RA (colapsos):', len(colapsos))
    print('total venues:', s.scalar(select(func.count()).select_from(Venue)))
    print('D-EDGE presente:', bool(s.scalars(select(Venue).where(Venue.name.ilike('%d-edge%'))).first()))
"
```
Expected: **colapsos: 0**; D-EDGE presente. Cole a saída.

- [ ] **Step 4: Idempotência — re-rodar ingest_ra não duplica**

Run:
```bash
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -c "
from nightlife.db import SessionLocal
from nightlife.models import Venue
from sqlalchemy import select, func
with SessionLocal() as s: print('antes:', s.scalar(select(func.count()).select_from(Venue)))
" && .venv/Scripts/python -m nightlife.ingest_ra >/dev/null && .venv/Scripts/python -c "
from nightlife.db import SessionLocal
from nightlife.models import Venue
from sqlalchemy import select, func
with SessionLocal() as s: print('depois:', s.scalar(select(func.count()).select_from(Venue)))
"
```
Expected: `antes` == `depois` (idempotente por source_url). Cole a saída.

---

## Coverage map (plano ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §3A classify sem geo → review/distinct | Task 1 |
| §3B upsert_venue identidade por source_url | Task 2 |
| §4 runner repair_ra_dedup | Task 3 |
| §5/§7 suíte verde + reparo real + smoke (colapsos=0, idempotente) | Task 4 |

**Fora deste plano (spec §6):** `normalize_name`/stopwords, re-dedup ao geocodar (Places), path de âncora de flyer, interface de revisão dos DedupeCandidate.
