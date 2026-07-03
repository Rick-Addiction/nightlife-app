# Nightlife App — Plano E: Score-da-evidência + Fonte OSM — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar a evidência (`venue_sources`/`event_sources`) a fonte da verdade do score (recompute após todo upsert, evidência idempotente, decay na leitura, faixa de review no venue match) e, sobre essa base, implementar a primeira fonte real: OpenStreetMap/Overpass (baladas + casas de evento de SP).

**Architecture:** Specs: `docs/superpowers/specs/2026-07-01-evidence-scoring-design.md` (Tasks 0–7) e `2026-07-01-osm-source-design.md` (Tasks 8–9). Novos módulos: `domain/freshness.py` (decay puro), `persistence/evidence.py` (escrita idempotente de evidência), `persistence/confidence.py` (sinais derivados da evidência + recompute + `verification_logs`), `ingestion/osm_source.py` (parse puro + fetch). `ingestion/signals.py` é **deletado**; os repos mudam de assinatura (`signals` sai, `reference` entra). A matemática de `domain/scoring.py` não muda.

**Tech Stack:** Python 3.14 · SQLAlchemy 2.0 · FastAPI · httpx (vira dep de runtime) · pytest. Postgres na porta 5434 (Docker).

**Convenções:**
- Rode tudo pelo venv: `.venv/Scripts/python -m ...`. cwd do shell RESETA entre chamadas Bash — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Testes de DB exigem `docker compose up -d --wait`. Contagem: `-o console_output_style=count` (pipe pra grep/tail engole o resumo neste Git Bash).
- Suíte atual: **66 passed**. Todo commit termina com: `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`
- **NÃO modifique** `config.py`, `docker-compose.yml`, `tests/conftest.py`, `.env.example`, `migrations/` (nenhuma migration é necessária — nenhuma coluna nova).

---

## File Structure

```
src/nightlife/
  domain/
    freshness.py            # freshness_factor  (Task 0)
    matching.py             # + classify_venue_match  (Task 1)
  persistence/
    evidence.py             # record_venue_evidence / record_event_evidence  (Task 2)
    confidence.py           # *_signals_from_evidence, recompute_*  (Task 3)
    venues_repo.py          # reescrito  (Task 4)
    events_repo.py          # reescrito  (Task 5)
  ingestion/
    signals.py              # DELETADO  (Task 6)
    pipeline.py             # simplificado  (Task 6)
    osm_source.py           # parse_overpass + OSMSource  (Task 8)
  api/
    schemas.py, main.py     # effective_confidence, default upcoming  (Task 7)
  ingest_osm.py             # runner  (Task 9)
tests/
  test_freshness.py (T0) · test_matching.py (T1) · test_evidence.py (T2)
  test_confidence.py (T3) · test_venues_repo.py (T4) · test_events_repo.py (T5)
  test_ingestion_signals.py DELETADO + test_pipeline.py (T6) · test_api.py (T7)
  test_osm_source.py (T8)
pyproject.toml (T9: httpx → runtime) · README.md (T9)
```

---

## Task 0: `domain/freshness.py` (decay puro)

**Files:**
- Create: `src/nightlife/domain/freshness.py`
- Test: `tests/test_freshness.py`

- [ ] **Step 1: Teste que falha** — create `tests/test_freshness.py`:

```python
# tests/test_freshness.py
from datetime import datetime, timedelta, timezone

from nightlife.domain.freshness import freshness_factor

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def test_fresh_within_30_days_is_full():
    assert freshness_factor(NOW - timedelta(days=10), NOW) == 1.0
    assert freshness_factor(NOW - timedelta(days=30), NOW) == 1.0
    assert freshness_factor(NOW, NOW) == 1.0


def test_linear_decay_then_floor():
    assert freshness_factor(NOW - timedelta(days=105), NOW) == 0.75  # meio caminho
    assert freshness_factor(NOW - timedelta(days=180), NOW) == 0.5
    assert freshness_factor(NOW - timedelta(days=400), NOW) == 0.5   # piso
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_freshness.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.domain.freshness'`.

- [ ] **Step 3: Implementar** — create `src/nightlife/domain/freshness.py`:

```python
# src/nightlife/domain/freshness.py
from __future__ import annotations

from datetime import datetime

_FULL_DAYS = 30.0    # ate aqui, frescor pleno
_FLOOR_DAYS = 180.0  # daqui em diante, piso
_FLOOR = 0.5


def freshness_factor(last_seen_at: datetime, now: datetime) -> float:
    """Fator multiplicativo de frescor: 1.0 ate 30 dias sem reconfirmacao,
    decai linearmente ate 0.5 aos 180 dias, e fica no piso 0.5.
    Aplicado na LEITURA (effective_confidence) — nightlife e efemero, mas
    registro antigo ainda vale metade, nunca zero."""
    age_days = max(0.0, (now - last_seen_at).total_seconds() / 86400.0)
    if age_days <= _FULL_DAYS:
        return 1.0
    if age_days >= _FLOOR_DAYS:
        return _FLOOR
    return 1.0 - (1.0 - _FLOOR) * (age_days - _FULL_DAYS) / (_FLOOR_DAYS - _FULL_DAYS)
```

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_freshness.py -q`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/domain/freshness.py tests/test_freshness.py && git commit -m "feat(domain): freshness_factor (decay linear 30->180d, piso 0.5)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 1: `classify_venue_match` (faixas de merge/review/distinct)

**Files:**
- Modify: `src/nightlife/domain/matching.py` (adicionar no fim do arquivo)
- Test: `tests/test_matching.py` (adicionar no fim)

- [ ] **Step 1: Teste que falha** — append em `tests/test_matching.py`:

```python
def test_classify_venue_match_bands():
    from nightlife.domain.matching import classify_venue_match

    assert classify_venue_match(0.90) == "auto_merge"
    assert classify_venue_match(0.85) == "auto_merge"
    assert classify_venue_match(0.78) == "review"
    assert classify_venue_match(0.70) == "review"
    assert classify_venue_match(0.60) == "distinct"
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_matching.py -q`
Expected: FAIL — `ImportError: cannot import name 'classify_venue_match'`.

- [ ] **Step 3: Implementar** — append em `src/nightlife/domain/matching.py`:

```python
VENUE_MERGE_THRESHOLD = 0.85
VENUE_REVIEW_THRESHOLD = 0.70


def classify_venue_match(score: float) -> str:
    """Faixas de decisao para upsert de venue: merge automatico so em alta
    confianca; a faixa intermediaria cria venue novo + candidato de revisao
    (um merge errado de venue envenena a ancora de todos os eventos)."""
    if score >= VENUE_MERGE_THRESHOLD:
        return "auto_merge"
    if score >= VENUE_REVIEW_THRESHOLD:
        return "review"
    return "distinct"
```

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_matching.py -q`
Expected: PASS (9 testes no arquivo).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/domain/matching.py tests/test_matching.py && git commit -m "feat(domain): classify_venue_match com faixa de review (0.70-0.85)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: `persistence/evidence.py` (evidência idempotente)

**Files:**
- Create: `src/nightlife/persistence/evidence.py`
- Test: `tests/test_evidence.py`

- [ ] **Step 1: Teste que falha** — create `tests/test_evidence.py`:

```python
# tests/test_evidence.py
from sqlalchemy import select

from nightlife.models import Event, EventSource, Venue, VenueSource
from nightlife.persistence.evidence import record_event_evidence, record_venue_evidence
from nightlife.persistence.inputs import SourceInfo


def _src(payload='{"a":1}', url="https://osm.org/node/1"):
    return SourceInfo(source_type="osm", source_url=url, raw_payload=payload,
                      extracted_fields={"p": payload})


def test_venue_evidence_is_idempotent(session):
    v = Venue(name="Lab Club")
    session.add(v)
    session.flush()

    record_venue_evidence(session, v.id, _src(), contribution=20)
    record_venue_evidence(session, v.id, _src(), contribution=20)  # mesma fonte de novo
    rows = session.scalars(select(VenueSource)).all()
    assert len(rows) == 1  # atualizou, nao duplicou
    assert rows[0].confidence_contribution == 20

    # payload mudou -> hash e extracted_fields atualizam, ainda 1 linha
    old_hash = rows[0].raw_payload_hash
    record_venue_evidence(session, v.id, _src(payload='{"a":2}'), contribution=20)
    rows = session.scalars(select(VenueSource)).all()
    assert len(rows) == 1 and rows[0].raw_payload_hash != old_hash

    # source_url diferente -> linha nova
    record_venue_evidence(session, v.id, _src(url="https://osm.org/node/2"), contribution=20)
    assert len(session.scalars(select(VenueSource)).all()) == 2


def test_event_evidence_idempotent_with_null_url(session):
    e = Event(name="Festa X")
    session.add(e)
    session.flush()
    s = SourceInfo(source_type="manual", source_url=None, raw_payload="x", extracted_fields={})
    record_event_evidence(session, e.id, s, contribution=0)
    record_event_evidence(session, e.id, s, contribution=0)
    assert len(session.scalars(select(EventSource)).all()) == 1  # NULL url tambem e chave
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_evidence.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.persistence.evidence'`.

- [ ] **Step 3: Implementar** — create `src/nightlife/persistence/evidence.py`:

```python
# src/nightlife/persistence/evidence.py
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EventSource, VenueSource
from ._utils import payload_hash
from .inputs import SourceInfo


def _record(session: Session, model, fk_col, entity_id: int, source: SourceInfo,
            contribution: int):
    """Upsert de evidencia por chave (entidade, source_type, source_url).

    Re-executar a mesma fonte atualiza last_seen_at (e o payload, se mudou)
    em vez de inserir linha duplicada — spec §3 'reprocessar so o que mudou'.
    Comparar coluna com None vira IS NULL no SQLAlchemy, entao url ausente
    tambem funciona como chave.
    """
    row = session.scalars(
        select(model).where(
            fk_col == entity_id,
            model.source_type == source.source_type,
            model.source_url == source.source_url,
        )
    ).first()
    now = datetime.now(timezone.utc)
    new_hash = payload_hash(source.raw_payload)
    if row is not None:
        row.fetched_at = now
        row.last_seen_at = now
        if row.raw_payload_hash != new_hash:
            row.raw_payload_hash = new_hash
            row.extracted_fields = source.extracted_fields
        row.confidence_contribution = contribution
    else:
        row = model(
            source_type=source.source_type,
            source_url=source.source_url,
            raw_payload_hash=new_hash,
            extracted_fields=source.extracted_fields,
            confidence_contribution=contribution,
        )
        setattr(row, fk_col.key, entity_id)
        session.add(row)
    # flush: a evidencia precisa estar visivel para o recompute que vem a seguir
    # (e para o proximo lookup em sessoes com autoflush=False, como a SessionLocal)
    session.flush()
    return row


def record_venue_evidence(session: Session, venue_id: int, source: SourceInfo,
                          *, contribution: int) -> VenueSource:
    return _record(session, VenueSource, VenueSource.venue_id, venue_id, source, contribution)


def record_event_evidence(session: Session, event_id: int, source: SourceInfo,
                          *, contribution: int) -> EventSource:
    return _record(session, EventSource, EventSource.event_id, event_id, source, contribution)
```

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_evidence.py -q`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/persistence/evidence.py tests/test_evidence.py && git commit -m "feat(persistence): evidencia idempotente por (entidade, source_type, source_url)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: `persistence/confidence.py` (sinais da evidência + recompute)

**Files:**
- Create: `src/nightlife/persistence/confidence.py`
- Test: `tests/test_confidence.py`

- [ ] **Step 1: Teste que falha** — create `tests/test_confidence.py`:

```python
# tests/test_confidence.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nightlife.models import Event, Venue, VerificationLog
from nightlife.persistence.confidence import (
    recompute_event_confidence,
    recompute_venue_confidence,
)
from nightlife.persistence.evidence import record_event_evidence, record_venue_evidence
from nightlife.persistence.inputs import SourceInfo

SP = ZoneInfo("America/Sao_Paulo")
REF = date(2026, 6, 1)


def _src(stype, url):
    return SourceInfo(source_type=stype, source_url=url, raw_payload="p", extracted_fields={})


def test_venue_confidence_accumulates_and_sees_future_event(session):
    v = Venue(name="Lab Club")
    session.add(v)
    session.flush()

    record_venue_evidence(session, v.id, _src("osm", "https://osm.org/1"), contribution=20)
    assert recompute_venue_confidence(session, v, reference=REF) == 20

    record_venue_evidence(session, v.id, _src("google_places", "https://g.co/1"), contribution=30)
    assert recompute_venue_confidence(session, v, reference=REF) == 50  # acumula, nao max()

    # evento futuro linkado -> +15 (a promessa do spec §7 que estava morta)
    session.add(Event(name="Festa", venue_id=v.id,
                      starts_at=datetime(2026, 6, 13, 23, 0, tzinfo=SP)))
    session.flush()
    assert recompute_venue_confidence(session, v, reference=REF) == 65

    logs = session.scalars(select(VerificationLog)).all()
    assert len(logs) == 3  # cada mudanca de score gera trilha


def test_event_multisource_bonus_and_recompute_down(session):
    v = Venue(name="Audio")
    session.add(v)
    session.flush()
    e = Event(name="Mamba Negra", venue_id=v.id,
              starts_at=datetime(2026, 6, 13, 23, 0, tzinfo=SP))
    session.add(e)
    session.flush()

    record_event_evidence(session, e.id, _src("ticketing", "https://t/1"), contribution=25)
    # future 20 + venue 20 + ticketing 25, 1 fonte
    assert recompute_event_confidence(session, e, reference=REF) == 65

    record_event_evidence(session, e.id, _src("instagram", "https://ig/1"), contribution=0)
    # 2 source_types distintos -> +20 multi-fonte
    assert recompute_event_confidence(session, e, reference=REF) == 85

    e.status = "cancelled"
    # recompute pode DESCER: 85 - 50 (cancelado) = 35
    assert recompute_event_confidence(session, e, reference=REF) == 35
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_confidence.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.persistence.confidence'`.

- [ ] **Step 3: Implementar** — create `src/nightlife/persistence/confidence.py`:

```python
# src/nightlife/persistence/confidence.py
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.scoring import EventSignals, VenueSignals, score_event, score_venue
from ..models import Event, EventSource, Venue, VenueSource, VerificationLog

# Quanto cada fonte vale SOZINHA (gravado em confidence_contribution — agora o
# nome e honesto). O score da entidade vem de score_venue/score_event sobre os
# sinais derivados da evidencia acumulada, nao da soma destes valores.
VENUE_SOURCE_CONTRIBUTION = {
    "google_places": 30, "osm": 20, "official_website": 20, "instagram": 15,
}
EVENT_SOURCE_CONTRIBUTION = {
    "ticketing": 25, "official_website": 25, "organizer": 25,
}


def venue_signals_from_evidence(session: Session, venue: Venue, *, reference: date) -> VenueSignals:
    types = set(session.scalars(
        select(VenueSource.source_type).where(VenueSource.venue_id == venue.id)
    ))
    has_future_event = session.scalars(
        select(Event.id).where(Event.venue_id == venue.id, Event.starts_at >= reference).limit(1)
    ).first() is not None
    return VenueSignals(
        google_places_operational="google_places" in types,
        osm_match="osm" in types,
        official_website="official_website" in types,
        instagram_link="instagram" in types,
        future_event_linked=has_future_event,
        closed=venue.status == "closed",
        permanently_closed=venue.status == "permanently_closed",
        # stale/unverified ficam False no v1: frescor e decay na leitura
    )


def event_signals_from_evidence(session: Session, event: Event, *, reference: date) -> EventSignals:
    types = set(session.scalars(
        select(EventSource.source_type).where(EventSource.event_id == event.id)
    ))
    starts = event.starts_at
    return EventSignals(
        future_date=starts is not None and starts.date() >= reference,
        venue_matched=event.venue_id is not None,
        official_source=bool(types & {"official_website", "organizer"}),
        ticketing_source="ticketing" in types,
        # COUNT DISTINCT source_type como proxy de independencia: 2 posts do
        # mesmo IG nao contam como 2 fontes
        independent_source_count=len(types) or 1,
        no_venue=event.venue_id is None,
        past_date=starts is not None and starts.date() < reference,
        cancelled=event.status == "cancelled",
    )


def _log_change(session: Session, entity_type: str, entity_id: int, old: int, new: int) -> None:
    session.add(VerificationLog(
        entity_type=entity_type, entity_id=entity_id,
        note=f"confidence {old} -> {new} (recompute)",
    ))


def recompute_venue_confidence(session: Session, venue: Venue, *, reference: date) -> int:
    new = score_venue(venue_signals_from_evidence(session, venue, reference=reference))
    if new != venue.confidence:
        _log_change(session, "venue", venue.id, venue.confidence, new)
        venue.confidence = new
    return venue.confidence


def recompute_event_confidence(session: Session, event: Event, *, reference: date) -> int:
    new = score_event(event_signals_from_evidence(session, event, reference=reference))
    if new != event.confidence:
        _log_change(session, "event", event.id, event.confidence, new)
        event.confidence = new
    return event.confidence
```

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_confidence.py -q`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/persistence/confidence.py tests/test_confidence.py && git commit -m "feat(persistence): score derivado da evidencia acumulada + verification_logs

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 4: Reescrever `venues_repo` (nova assinatura + faixa de review)

**Files:**
- Modify: `src/nightlife/persistence/venues_repo.py` (conteúdo completo abaixo)
- Modify: `tests/test_venues_repo.py` (conteúdo completo abaixo)

> A partir desta task e até o fim da Task 6, a suíte fica temporariamente quebrada em outros arquivos (events_repo/pipeline ainda usam a assinatura velha) — rode só os arquivos de teste indicados em cada step. A Task 6 fecha a transição e volta a rodar a suíte inteira.

- [ ] **Step 1: Reescrever o teste** — replace `tests/test_venues_repo.py` inteiro:

```python
# tests/test_venues_repo.py
from datetime import date

from sqlalchemy import select

from nightlife.models import DedupeCandidate, Venue, VenueSource
from nightlife.persistence.inputs import SourceInfo, VenueInput
from nightlife.persistence.venues_repo import upsert_venue

REF = date(2026, 6, 1)


def _src(stype="google_places", url="http://x"):
    return SourceInfo(source_type=stype, source_url=url,
                      raw_payload='{"k":1}', extracted_fields={"k": 1})


def test_creates_new_venue_with_score_and_evidence(session):
    v = upsert_venue(
        session,
        VenueInput(name="Lab Club", lat=-23.561, lng=-46.656, address="R. X", category="nightclub"),
        _src("google_places", "http://g"),
        reference=REF,
    )
    assert v.id is not None
    assert v.confidence == 30  # evidencia acumulada: so google_places
    srcs = session.scalars(select(VenueSource)).all()
    assert len(srcs) == 1 and srcs[0].confidence_contribution == 30


def test_auto_merge_accumulates_confidence(session):
    upsert_venue(session, VenueInput(name="Lab Club", lat=-23.561, lng=-46.656),
                 _src("google_places", "http://g"), reference=REF)
    v = upsert_venue(session, VenueInput(name="lab club", lat=-23.5611, lng=-46.6561),
                     _src("osm", "https://osm.org/1"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 1      # nao duplicou
    assert len(session.scalars(select(VenueSource)).all()) == 2  # duas evidencias
    assert v.confidence == 50  # places(30) + osm(20) ACUMULADOS


def test_rerun_same_source_is_idempotent(session):
    upsert_venue(session, VenueInput(name="Lab Club"), _src("osm", "https://osm.org/1"), reference=REF)
    v = upsert_venue(session, VenueInput(name="Lab Club"), _src("osm", "https://osm.org/1"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 1
    assert len(session.scalars(select(VenueSource)).all()) == 1  # evidencia nao duplica
    assert v.confidence == 20


def test_distinct_names_create_two_venues(session):
    upsert_venue(session, VenueInput(name="Lab Club"), _src(), reference=REF)
    upsert_venue(session, VenueInput(name="Trackers"), _src(url="http://y"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 2
    assert session.scalars(select(DedupeCandidate)).all() == []


def test_mid_similarity_creates_new_plus_review_candidate(session):
    # "Audio SP" x "Audio Club" -> similaridade ~0.77 (faixa 0.70-0.85):
    # cria venue novo E registra candidato de revisao, sem merge automatico
    upsert_venue(session, VenueInput(name="Audio Club"), _src(url="http://a"), reference=REF)
    upsert_venue(session, VenueInput(name="Audio SP"), _src(url="http://b"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 2
    cands = session.scalars(select(DedupeCandidate)).all()
    assert len(cands) == 1
    assert cands[0].kind == "venue" and cands[0].decision == "review"
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest tests/test_venues_repo.py -q`
Expected: FAIL — `TypeError` (assinatura antiga exige `signals`).

- [ ] **Step 3: Reescrever** — replace `src/nightlife/persistence/venues_repo.py` inteiro:

```python
# src/nightlife/persistence/venues_repo.py
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.matching import VenueRef, classify_venue_match, match_venue
from ..models import DedupeCandidate, Venue
from .confidence import VENUE_SOURCE_CONTRIBUTION, recompute_venue_confidence
from .evidence import record_venue_evidence
from .inputs import SourceInfo, VenueInput


def upsert_venue(
    session: Session, candidate: VenueInput, source: SourceInfo, *, reference: date
) -> Venue:
    existing = session.scalars(select(Venue)).all()
    refs = [VenueRef(v.id, v.name, v.address, v.lat, v.lng) for v in existing]
    # threshold=0.0: queremos o melhor match SEMPRE; a decisao vem das faixas
    best = match_venue(
        VenueRef(None, candidate.name, candidate.address, candidate.lat, candidate.lng),
        refs, threshold=0.0,
    )
    decision = classify_venue_match(best.score) if best is not None else "distinct"

    if decision == "auto_merge":
        venue = session.get(Venue, best.venue.id)
        venue.last_seen_at = datetime.now(timezone.utc)
        # preenche lacunas sem sobrescrever dados ja existentes
        venue.lat = venue.lat if venue.lat is not None else candidate.lat
        venue.lng = venue.lng if venue.lng is not None else candidate.lng
        venue.address = venue.address or candidate.address
        venue.category = venue.category or candidate.category
    else:
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

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_venues_repo.py tests/test_evidence.py tests/test_confidence.py -q`
Expected: PASS (9 testes). (A suíte inteira ainda quebra em events_repo/pipeline — esperado até a Task 6.)

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/persistence/venues_repo.py tests/test_venues_repo.py && git commit -m "refactor(persistence): upsert_venue deriva score da evidencia + faixa de review

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 5: Reescrever `events_repo`

**Files:**
- Modify: `src/nightlife/persistence/events_repo.py` (conteúdo completo abaixo)
- Modify: `tests/test_events_repo.py` (conteúdo completo abaixo)

- [ ] **Step 1: Reescrever o teste** — replace `tests/test_events_repo.py` inteiro:

```python
# tests/test_events_repo.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nightlife.models import DedupeCandidate, Event, EventSource, Venue
from nightlife.persistence.inputs import EventInput, SourceInfo
from nightlife.persistence.events_repo import upsert_event

SP = ZoneInfo("America/Sao_Paulo")
REF = date(2026, 6, 1)


def _venue(session, name="Lab Club"):
    v = Venue(name=name)
    session.add(v)
    session.flush()
    return v


def _src(stype="ticketing", url="http://t"):
    return SourceInfo(source_type=stype, source_url=url, raw_payload="p", extracted_fields={})


def _evin(name, dt, venue, ticket=None):
    return EventInput(name=name, starts_at=dt, venue_id=venue.id, venue_name=venue.name, ticket_url=ticket)


def test_creates_event_with_score_and_source(session):
    v = _venue(session)
    e = upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v),
                     _src(), reference=REF)
    assert e.id is not None
    assert e.confidence == 20 + 20 + 25  # future + venue + ticketing
    assert len(session.scalars(select(EventSource)).all()) == 1


def test_duplicate_merges_and_multisource_bonus_fires(session):
    v = _venue(session)
    upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v),
                 _src("ticketing", "http://t"), reference=REF)
    e = upsert_event(session, _evin("MAMBA NEGRA", datetime(2026, 6, 13, 23, 30, tzinfo=SP), v),
                     _src("instagram", "http://ig"), reference=REF)
    assert len(session.scalars(select(Event)).all()) == 1       # merge
    assert len(session.scalars(select(EventSource)).all()) == 2  # duas evidencias
    # 2 source_types distintos -> +20 multi-fonte (spec §7, antes morto)
    assert e.confidence == 20 + 20 + 25 + 20


def test_distinct_events_create_two(session):
    v1 = _venue(session, "Lab Club")
    v2 = _venue(session, "Cargo")
    upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v1),
                 _src(), reference=REF)
    upsert_event(session, _evin("Gop Tun", datetime(2026, 7, 20, 16, 0, tzinfo=SP), v2),
                 _src(url="http://t2"), reference=REF)
    assert len(session.scalars(select(Event)).all()) == 2


def test_medium_confidence_creates_dedupe_candidate(session):
    v = _venue(session)
    upsert_event(session, _evin("Festa X", datetime(2026, 6, 13, 22, 0, tzinfo=SP), v),
                 _src(), reference=REF)
    upsert_event(session, _evin("Festa X", datetime(2026, 6, 14, 14, 0, tzinfo=SP), v),
                 _src("instagram", "http://ig"), reference=REF)
    assert len(session.scalars(select(Event)).all()) == 2
    cands = session.scalars(select(DedupeCandidate)).all()
    assert len(cands) == 1 and cands[0].decision == "review" and cands[0].kind == "event"


def test_linked_venue_gains_future_event_bonus(session):
    v = _venue(session)
    assert v.confidence == 0
    upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v),
                 _src(), reference=REF)
    # o upsert do evento recomputa o venue linkado: +15 future_event_linked
    assert v.confidence == 15
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_events_repo.py -q`
Expected: FAIL — `TypeError` (assinatura antiga exige `signals`).

- [ ] **Step 3: Reescrever** — replace `src/nightlife/persistence/events_repo.py` inteiro:

```python
# src/nightlife/persistence/events_repo.py
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.dedupe import EventKey, compare
from ..models import DedupeCandidate, Event, Venue
from .confidence import (
    EVENT_SOURCE_CONTRIBUTION,
    recompute_event_confidence,
    recompute_venue_confidence,
)
from .evidence import record_event_evidence
from .inputs import EventInput, SourceInfo


def _key_from_input(c: EventInput) -> EventKey:
    return EventKey(name=c.name, starts_at=c.starts_at, venue_name=c.venue_name,
                    organizer=c.organizer, ticket_url=c.ticket_url)


def _key_from_row(e: Event) -> EventKey:
    # organizer so existe quando organizer_id foi linkado (fonte futura fara isso)
    venue_name = e.venue.name if e.venue is not None else None
    organizer = e.organizer.name if e.organizer is not None else None
    return EventKey(name=e.name, starts_at=e.starts_at, venue_name=venue_name,
                    organizer=organizer, ticket_url=e.ticket_url)


def upsert_event(
    session: Session, candidate: EventInput, source: SourceInfo, *, reference: date
) -> Event:
    cand_key = _key_from_input(candidate)
    existing = session.scalars(select(Event)).all()

    best_row = None
    best = None
    for row in existing:
        result = compare(cand_key, _key_from_row(row))
        if best is None or result.score > best.score:
            best, best_row = result, row

    if best is not None and best.decision == "auto_merge":
        event = best_row
        event.last_seen_at = datetime.now(timezone.utc)
        # preenche lacunas sem sobrescrever dados ja existentes:
        # ex. flyer sem data parseavel + pagina de ticketing com startDate real
        event.starts_at = event.starts_at if event.starts_at is not None else candidate.starts_at
        event.ends_at = event.ends_at if event.ends_at is not None else candidate.ends_at
        event.venue_id = event.venue_id if event.venue_id is not None else candidate.venue_id
        event.ticket_url = event.ticket_url or candidate.ticket_url
        event.genre = event.genre or candidate.genre
        event.lineup_text = event.lineup_text or candidate.lineup_text
    else:
        event = Event(
            name=candidate.name, starts_at=candidate.starts_at, ends_at=candidate.ends_at,
            venue_id=candidate.venue_id, lineup_text=candidate.lineup_text,
            genre=candidate.genre, ticket_url=candidate.ticket_url,
            raw_fields=candidate.raw_fields, status="scheduled",
        )
        session.add(event)
        session.flush()
        if best is not None and best.decision == "review":
            session.add(DedupeCandidate(
                kind="event", a_id=event.id, b_id=best_row.id,
                similarity_score=best.score, decision="review",
            ))

    record_event_evidence(
        session, event.id, source,
        contribution=EVENT_SOURCE_CONTRIBUTION.get(source.source_type, 0),
    )
    recompute_event_confidence(session, event, reference=reference)
    # um evento futuro linkado muda o sinal future_event_linked do venue
    if event.venue_id is not None:
        venue = session.get(Venue, event.venue_id)
        if venue is not None:
            recompute_venue_confidence(session, venue, reference=reference)
    return event
```

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_events_repo.py tests/test_venues_repo.py -q`
Expected: PASS (10 testes).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/persistence/events_repo.py tests/test_events_repo.py && git commit -m "refactor(persistence): upsert_event deriva score da evidencia + recomputa venue linkado

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 6: Pipeline sem `signals.py` (fecha a transição)

**Files:**
- Modify: `src/nightlife/ingestion/pipeline.py` (conteúdo completo abaixo)
- Delete: `src/nightlife/ingestion/signals.py`, `tests/test_ingestion_signals.py`
- Modify: `tests/test_pipeline.py` (só as 2 mudanças indicadas)

- [ ] **Step 1: Atualizar os testes do pipeline** — em `tests/test_pipeline.py`, no teste `test_pipeline_creates_venue_event_and_run`, troque a asserção do venue e a do run (o resto do arquivo fica igual):

```python
    venues = session.scalars(select(Venue)).all()
    # google_places(30) + future_event_linked(15): o evento ingerido na mesma
    # rodada recomputa o venue linkado
    assert len(venues) == 1 and venues[0].confidence == 45
```

E no `test_pipeline_event_without_resolvable_venue`, adicione ao final:

```python
    # sem venue e sem ticketing: future(20) - no_venue(20) = 0
    assert events[0].confidence == 0
```

- [ ] **Step 2: Reescrever o pipeline** — replace `src/nightlife/ingestion/pipeline.py` inteiro:

```python
# src/nightlife/ingestion/pipeline.py
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.matching import VenueRef, match_venue
from ..extraction.base import ExtractedEvent
from ..extraction.freetext import extract_freetext_deterministic
from ..extraction.html_patterns import parse_html_patterns
from ..extraction.jsonld import parse_jsonld_events
from ..models import IngestionRun, Venue
from ..persistence.events_repo import upsert_event
from ..persistence.inputs import EventInput, SourceInfo, VenueInput
from ..persistence.venues_repo import upsert_venue
from .base import RawEventPage, Source


def _extract_page(page: RawEventPage, reference: date) -> list[ExtractedEvent]:
    if page.kind == "jsonld":
        return parse_jsonld_events(page.content, source_url=page.source_url)
    if page.kind == "html":
        return parse_html_patterns(page.content, source_url=page.source_url)
    if page.kind == "freetext":
        return [extract_freetext_deterministic(page.content, reference=reference, source_url=page.source_url)]
    raise ValueError(f"kind de pagina desconhecido: {page.kind!r}")


def _resolve_venue(session: Session, venue_name: str | None) -> Venue | None:
    if not venue_name:
        return None
    existing = session.scalars(select(Venue)).all()
    refs = [VenueRef(v.id, v.name, v.address, v.lat, v.lng) for v in existing]
    m = match_venue(VenueRef(None, venue_name), refs)
    return session.get(Venue, m.venue.id) if m is not None else None


def run_ingestion(session: Session, source: Source, *, reference: date, label: str = "mock") -> IngestionRun:
    run = IngestionRun(source=label, status="running")
    session.add(run)
    session.flush()

    found = created = 0
    errors: list[str] = []

    for rv in source.venues():
        found += 1
        try:
            upsert_venue(
                session,
                VenueInput(name=rv.name, lat=rv.lat, lng=rv.lng, address=rv.address, category=rv.category),
                SourceInfo(source_type=rv.source_type, source_url=rv.source_url, raw_payload=rv.raw_payload),
                reference=reference,
            )
            created += 1
        except Exception as exc:  # noqa: BLE001 — registra e segue
            errors.append(f"venue {rv.name!r}: {exc}")

    for page in source.event_pages():
        found += 1
        try:
            extracted = _extract_page(page, reference)
        except Exception as exc:  # noqa: BLE001 — extracao da pagina falhou
            errors.append(f"page {page.source_url!r} (extract): {exc}")
            continue
        for ev in extracted:
            if not ev.name:
                continue
            try:
                venue = _resolve_venue(session, ev.venue_name)
                upsert_event(
                    session,
                    EventInput(
                        name=ev.name, starts_at=ev.starts_at,
                        venue_id=venue.id if venue is not None else None,
                        venue_name=ev.venue_name, ticket_url=ev.ticket_url,
                        raw_fields=ev.raw,
                    ),
                    SourceInfo(source_type=page.source_type, source_url=page.source_url, raw_payload=page.content),
                    reference=reference,
                )
                created += 1
            except Exception as exc:  # noqa: BLE001 — registra o evento e segue
                errors.append(f"page {page.source_url!r} event {ev.name!r}: {exc}")

    run.status = "finished"
    run.records_found = found
    run.records_created = created
    run.finished_at = datetime.now(timezone.utc)
    run.errors = "\n".join(errors) or None
    session.flush()
    return run
```

- [ ] **Step 3: Deletar o módulo de sinais e seu teste**

```bash
cd /d/MyProjects/nightlife-app && git rm src/nightlife/ingestion/signals.py tests/test_ingestion_signals.py
```

- [ ] **Step 4: Verificar que nada mais importa signals e rodar a SUÍTE INTEIRA**

Run: `cd /d/MyProjects/nightlife-app && grep -rn "ingestion.signals\|derive_venue_signals\|derive_event_signals" src/ tests/ || echo "sem referencias"`
Expected: `sem referencias`.

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest -q -o console_output_style=count -p no:warnings`
Expected: **73 passed** (66 + 2 freshness + 1 classify + 2 evidence + 2 confidence + 1 venues [4→5] + 1 events [4→5] − 2 signals = 73; a linha final mostra `[73/73]`).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add -A && git commit -m "refactor(ingestion): pipeline delega score aos repos; remove signals.py

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 7: API — `effective_confidence` (decay) + default upcoming

**Files:**
- Modify: `src/nightlife/api/schemas.py` (adicionar campo nos dois schemas)
- Modify: `src/nightlife/api/main.py` (conteúdo completo abaixo)
- Modify: `tests/test_api.py` (adicionar 2 testes no fim)

- [ ] **Step 1: Testes que falham** — append em `tests/test_api.py`:

```python
def test_effective_confidence_decays_with_staleness(session):
    from datetime import timedelta, timezone as tz
    old = datetime.now(tz.utc) - timedelta(days=180)
    v = Venue(name="Velho Club", status="operational", confidence=80)
    session.add(v)
    session.flush()
    v.last_seen_at = old  # nao reconfirmado ha 180 dias -> fator 0.5
    session.flush()
    client = _client(session)
    try:
        r = client.get(f"/venues/{v.id}")
        body = r.json()
        assert body["confidence"] == 80
        assert body["effective_confidence"] == 40
        # min_confidence filtra pelo effective
        r2 = client.get("/venues", params={"min_confidence": 50})
        assert all(x["id"] != v.id for x in r2.json())
    finally:
        app.dependency_overrides.clear()


def test_events_default_hides_past(session):
    v = Venue(name="X")
    session.add(v)
    session.flush()
    past = Event(name="Ontem", starts_at=datetime(2000, 1, 1, 23, 0, tzinfo=SP),
                 venue_id=v.id, status="scheduled", confidence=50)
    future = Event(name="Amanha", starts_at=datetime(2099, 1, 1, 23, 0, tzinfo=SP),
                   venue_id=v.id, status="scheduled", confidence=50)
    session.add_all([past, future])
    session.flush()
    client = _client(session)
    try:
        names = [x["name"] for x in client.get("/events").json()]
        assert "Amanha" in names and "Ontem" not in names  # default: so futuro
        names2 = [x["name"] for x in client.get("/events", params={"include_past": "true"}).json()]
        assert "Ontem" in names2
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_api.py -q`
Expected: FAIL — `KeyError: 'effective_confidence'` (e/ou "Ontem" presente no default).

- [ ] **Step 3: Implementar**

Em `src/nightlife/api/schemas.py`, adicione a AMBOS os schemas (`VenueOut` e `EventOut`), logo após o campo `confidence`:

```python
    effective_confidence: int = 0
```

Replace `src/nightlife/api/main.py` inteiro:

```python
# src/nightlife/api/main.py
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.freshness import freshness_factor
from ..models import Event, Venue
from .deps import get_session
from .schemas import EventOut, VenueOut

app = FastAPI(title="Nightlife SP — API")


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        min_lng, min_lat, max_lng, max_lat = (float(x) for x in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bbox deve ser 'minLng,minLat,maxLng,maxLat'") from exc
    return min_lng, min_lat, max_lng, max_lat


def _with_effective(out_cls, entity, now: datetime):
    out = out_cls.model_validate(entity)
    out.effective_confidence = round(entity.confidence * freshness_factor(entity.last_seen_at, now))
    return out


@app.get("/venues", response_model=list[VenueOut])
def list_venues(
    type: str | None = None,
    bbox: str | None = None,
    min_confidence: int = 0,
    session: Session = Depends(get_session),
):
    # pre-filtro no SQL pelo score armazenado e valido: effective <= stored
    q = select(Venue).where(Venue.confidence >= min_confidence)
    if type is not None:
        q = q.where(Venue.category == type)
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = _parse_bbox(bbox)
        q = q.where(
            Venue.lat >= min_lat, Venue.lat <= max_lat,
            Venue.lng >= min_lng, Venue.lng <= max_lng,
        )
    now = datetime.now(timezone.utc)
    outs = [_with_effective(VenueOut, v, now) for v in session.scalars(q).all()]
    outs = [o for o in outs if o.effective_confidence >= min_confidence]
    outs.sort(key=lambda o: o.effective_confidence, reverse=True)
    return outs


@app.get("/venues/{venue_id}", response_model=VenueOut)
def get_venue(venue_id: int, session: Session = Depends(get_session)):
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue nao encontrado")
    return _with_effective(VenueOut, venue, datetime.now(timezone.utc))


@app.get("/events", response_model=list[EventOut])
def list_events(
    date_from: date | None = None,
    date_to: date | None = None,
    bbox: str | None = None,
    genre: str | None = None,
    min_confidence: int = 0,
    include_past: bool = False,
    session: Session = Depends(get_session),
):
    if date_from is None and not include_past:
        # default: so eventos futuros — a lista nao acumula passado eternamente
        date_from = date.today()
    q = select(Event).where(Event.confidence >= min_confidence)
    if date_from is not None:
        q = q.where(Event.starts_at >= date_from)
    if date_to is not None:
        q = q.where(Event.starts_at <= date_to)
    if genre is not None:
        q = q.where(Event.genre == genre)
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = _parse_bbox(bbox)
        q = q.join(Venue, Event.venue_id == Venue.id).where(
            Venue.lat >= min_lat, Venue.lat <= max_lat,
            Venue.lng >= min_lng, Venue.lng <= max_lng,
        )
    now = datetime.now(timezone.utc)
    outs = [_with_effective(EventOut, e, now)
            for e in session.scalars(q.order_by(Event.starts_at)).all()]
    return [o for o in outs if o.effective_confidence >= min_confidence]


@app.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="evento nao encontrado")
    return _with_effective(EventOut, event, datetime.now(timezone.utc))
```

- [ ] **Step 4: Ver passar (suíte inteira)**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest -q -o console_output_style=count -p no:warnings`
Expected: **75 passed** (`[75/75]`).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/api/ tests/test_api.py && git commit -m "feat(api): effective_confidence com decay na leitura + /events default upcoming

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 8: Fonte OSM — `parse_overpass` + `OSMSource`

**Files:**
- Create: `src/nightlife/ingestion/osm_source.py`
- Test: `tests/test_osm_source.py`

- [ ] **Step 1: Teste que falha** — create `tests/test_osm_source.py`:

```python
# tests/test_osm_source.py
from nightlife.ingestion.base import RawVenue
from nightlife.ingestion.mock_source import MockSource  # noqa: F401 (referencia de padrao)
from nightlife.ingestion.osm_source import OSMSource, parse_overpass

OVERPASS_JSON = {
    "elements": [
        {  # node completo
            "type": "node", "id": 111, "lat": -23.5613, "lon": -46.6565,
            "tags": {"amenity": "nightclub", "name": "Lab Club",
                     "addr:street": "R. Augusta", "addr:housenumber": "1000"},
        },
        {  # way com center (sem lat/lon proprios)
            "type": "way", "id": 222,
            "center": {"lat": -23.529, "lon": -46.672},
            "tags": {"amenity": "events_venue", "name": "Audio SP"},
        },
        {  # sem name -> descartado
            "type": "node", "id": 333, "lat": -23.5, "lon": -46.6,
            "tags": {"amenity": "nightclub"},
        },
        {  # sem coordenada utilizavel -> descartado
            "type": "relation", "id": 444,
            "tags": {"amenity": "events_venue", "name": "Fantasma"},
        },
    ]
}


def test_parse_overpass_maps_and_discards():
    venues = parse_overpass(OVERPASS_JSON)
    assert [v.name for v in venues] == ["Lab Club", "Audio SP"]
    lab, audio = venues
    assert isinstance(lab, RawVenue)
    assert lab.source_type == "osm" and lab.category == "nightclub"
    assert (lab.lat, lab.lng) == (-23.5613, -46.6565)
    assert lab.address == "R. Augusta, 1000"
    assert lab.source_url == "https://www.openstreetmap.org/node/111"
    assert audio.lat == -23.529 and audio.address is None  # veio do center
    assert audio.source_url == "https://www.openstreetmap.org/way/222"


def test_osm_source_event_pages_is_empty():
    assert OSMSource().event_pages() == []
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_osm_source.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightlife.ingestion.osm_source'`.

- [ ] **Step 3: Implementar** — create `src/nightlife/ingestion/osm_source.py`:

```python
# src/nightlife/ingestion/osm_source.py
from __future__ import annotations

import json

import httpx

from .base import RawEventPage, RawVenue

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
# bbox da cidade de Sao Paulo: (south, west, north, east)
SP_BBOX = (-24.00, -46.83, -23.36, -46.36)
_USER_AGENT = "nightlife-app/0.1 (uso pessoal; https://github.com/ não-publicado)"


def _build_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    bb = f"{s},{w},{n},{e}"
    return (
        "[out:json][timeout:60];"
        f'(nwr["amenity"="nightclub"]({bb});'
        f'nwr["amenity"="events_venue"]({bb}););'
        "out center tags;"
    )


def parse_overpass(data: dict) -> list[RawVenue]:
    """JSON do Overpass -> RawVenues. Puro: testavel sem rede.

    Descarta elementos sem `name` ou sem coordenada utilizavel (node sem
    lat/lon e way/relation sem `center`).
    """
    out: list[RawVenue] = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        lat, lng = el.get("lat"), el.get("lon")
        if lat is None or lng is None:
            center = el.get("center") or {}
            lat, lng = center.get("lat"), center.get("lon")
        if lat is None or lng is None:
            continue
        street = tags.get("addr:street")
        number = tags.get("addr:housenumber")
        address = f"{street}, {number}" if street and number else street
        out.append(RawVenue(
            name=name,
            source_type="osm",
            lat=lat,
            lng=lng,
            address=address,
            category=tags.get("amenity"),
            source_url=f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
            # sort_keys: hash de payload estavel entre execucoes (idempotencia)
            raw_payload=json.dumps(el, ensure_ascii=False, sort_keys=True),
        ))
    return out


class OSMSource:
    """Fonte real #1: venues de nightlife de SP via Overpass API (OSM)."""

    def __init__(self, *, endpoint: str = OVERPASS_ENDPOINT,
                 bbox: tuple[float, float, float, float] = SP_BBOX,
                 timeout: float = 90.0) -> None:
        self._endpoint = endpoint
        self._bbox = bbox
        self._timeout = timeout

    def venues(self) -> list[RawVenue]:
        resp = httpx.post(
            self._endpoint,
            data={"data": _build_query(self._bbox)},
            headers={"User-Agent": _USER_AGENT},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return parse_overpass(resp.json())

    def event_pages(self) -> list[RawEventPage]:
        return []
```

- [ ] **Step 4: Ver passar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_osm_source.py -q`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/osm_source.py tests/test_osm_source.py && git commit -m "feat(ingestion): fonte OSM/Overpass (nightclub + events_venue, bbox SP)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 9: Runner `ingest_osm` + deps + README + smoke real

**Files:**
- Create: `src/nightlife/ingest_osm.py`
- Modify: `pyproject.toml` (httpx → runtime)
- Modify: `README.md` (seção OSM)

- [ ] **Step 1: Mover httpx para runtime** — em `pyproject.toml`, adicione `"httpx>=0.27",` ao bloco `dependencies` (após `"alembic>=1.13",`) e remova `"httpx>=0.27"` do `dev` (deixando `dev = ["pytest>=8.0"]`). Depois:

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pip install -e ".[dev]" && .venv/Scripts/python -c "import httpx; print(httpx.__version__)"`
Expected: instala sem erro e imprime a versão.

- [ ] **Step 2: Criar o runner** — create `src/nightlife/ingest_osm.py`:

```python
# src/nightlife/ingest_osm.py
"""Ingere venues reais de SP do OpenStreetMap (Overpass) no banco.

Uso: .venv/Scripts/python -m nightlife.ingest_osm
Re-executar e seguro: matching reusa venues e a evidencia e idempotente.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from .db import SessionLocal
from .ingestion.osm_source import OSMSource
from .ingestion.pipeline import run_ingestion
from .models import DedupeCandidate, Venue


def main() -> None:
    source = OSMSource()
    with SessionLocal() as session:
        run = run_ingestion(session, source, reference=date.today(), label="osm")
        session.commit()
        venues = session.scalar(select(func.count()).select_from(Venue))
        reviews = session.scalar(
            select(func.count()).select_from(DedupeCandidate).where(
                DedupeCandidate.kind == "venue", DedupeCandidate.decision == "review",
            )
        )
        print(f"IngestionRun #{run.id}: status={run.status} "
              f"found={run.records_found} created={run.records_created}")
        print(f"DB agora: {venues} venues | venue matches em review: {reviews}")
        if run.errors:
            print("erros:\n" + run.errors)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: README** — em `README.md`, logo após o bloco de "Rodando" (depois da linha do uvicorn), adicione:

```markdown
### Ingestão real: OpenStreetMap

```bash
.venv/Scripts/python -m nightlife.ingest_osm   # baladas + casas de evento de SP (Overpass)
```

Re-executar é seguro (matching reusa venues; evidência é idempotente). O runner
imprime quantos pares de venue caíram na fila de revisão (`dedupe_candidates`)
— material para calibrar os thresholds de matching com dados reais.
```

- [ ] **Step 4: Suíte inteira + smoke REAL contra o Overpass**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest -q -o console_output_style=count -p no:warnings`
Expected: **77 passed** (`[77/77]`).

Run (rede real; pode levar ~1 min): `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m alembic upgrade head && .venv/Scripts/python -m nightlife.ingest_osm`
Expected: `IngestionRun #N: status=finished found=<dezenas-a-centenas> created=...` e `DB agora: N venues | venue matches em review: M`. Rode UMA SEGUNDA VEZ e confirme que a contagem de venues **não** explode (idempotência + matching).

Se o Overpass der timeout/erro 429/504: tente 1 vez o endpoint alternativo `OSMSource(endpoint="https://overpass.kumi.systems/api/interpreter")` via um one-liner; se também falhar, reporte a saída (DONE_WITH_CONCERNS) — não fique em loop de retry.

- [ ] **Step 5: Commit**

```bash
cd /d/MyProjects/nightlife-app && git add pyproject.toml src/nightlife/ingest_osm.py README.md && git commit -m "feat(ingestion): runner ingest_osm + httpx runtime + README

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Coverage map (Plano E ↔ specs)

| Requisito do spec | Onde |
|---|---|
| evidence §3.1 idempotência por (entidade, source_type, source_url) | Task 2 |
| evidence §3.2 sinais da evidência + recompute + verification_logs + contribuições standalone | Task 3 |
| evidence §3.3 assinaturas novas (sem `signals`, com `reference`); score pode descer | Tasks 4–5 |
| evidence §3.4 faixa de review no venue match (`classify_venue_match`) | Tasks 1, 4 |
| evidence §3.5 decay na leitura (`freshness_factor` + `effective_confidence`) | Tasks 0, 7 |
| evidence §3.6 `/events` default upcoming + `include_past` | Task 7 |
| evidence §4 `signals.py` deletado; pipeline via repos; schema intacto | Task 6 |
| evidence §5 testes (idempotência, multi-fonte, future_event_linked, desce, freshness, review band, API) | Tasks 0–7 |
| osm §3–5 `parse_overpass` puro + `OSMSource` + query nightclub/events_venue + mapeamento | Task 8 |
| osm §6 teste offline + smoke real (2ª execução não duplica) + contagem de reviews | Tasks 8–9 |
| osm §7 httpx runtime + User-Agent + timeout | Tasks 8–9 |

**Fora deste plano:** ticketing (Sympla/Shotgun), digest Telegram, vision/IG, UI — próximos do roadmap (spec principal §16).
