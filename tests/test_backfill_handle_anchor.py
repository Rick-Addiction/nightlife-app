# tests/test_backfill_handle_anchor.py
import json
from datetime import datetime, timezone

from nightlife.backfill_handle_anchor import backfill
from nightlife.models import Event, EventSource, Venue, VerificationLog


def test_backfill_ancora_evento_flutuante_pelo_sidecar(session, tmp_path):
    v = Venue(name="Aura Club", instagram="aura.clubsp", lat=-23.55, lng=-46.66, confidence=50)
    session.add(v)
    session.flush()
    ev = Event(name="Expand Your Aura", status="scheduled", confidence=40,
               starts_at=datetime(2099, 7, 11, 2, 0, tzinfo=timezone.utc))
    session.add(ev)
    session.flush()
    session.add(EventSource(event_id=ev.id, source_type="vision_flyer",
                            source_url="https://www.instagram.com/p/DagZZD/"))
    session.flush()
    (tmp_path / "DagZZD.json").write_text(json.dumps({"handle": "aura.clubsp"}), encoding="utf-8")

    n = backfill(session, processed_dir=tmp_path)

    assert n == 1
    assert ev.venue_id == v.id
    # B6: trilha de evidencia via VerificationLog, mesmo padrao usado em merge_venues
    log = session.query(VerificationLog).filter_by(entity_type="event", entity_id=ev.id).one()
    assert "anchored_by=ig_handle" in log.note


def test_backfill_ignora_sem_sidecar_e_ja_ancorado(session, tmp_path):
    v = Venue(name="X", instagram="x", confidence=50)
    session.add(v)
    session.flush()
    ok = Event(name="Ja ancorado", status="scheduled", confidence=40, venue_id=v.id)
    solto = Event(name="Sem sidecar", status="scheduled", confidence=40)
    session.add_all([ok, solto])
    session.flush()
    session.add(EventSource(event_id=solto.id, source_type="vision_flyer",
                            source_url="https://www.instagram.com/p/NAOEXISTE/"))
    session.flush()
    assert backfill(session, processed_dir=tmp_path) == 0
    assert solto.venue_id is None
