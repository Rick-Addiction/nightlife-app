# tests/test_discover_ig_handles.py
from datetime import datetime, timedelta, timezone

from nightlife.discover_ig_handles import discover, no_ig_venues
from nightlife.ingestion.handle_match import ProfileSignals
from nightlife.ingestion.ig_search import SearchResult
from nightlife.models import Event, VerificationLog, Venue


def _nightclub(session, name, *, website=None, instagram=None):
    v = Venue(name=name, category="nightclub", website=website, instagram=instagram,
              lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    return v


def test_discover_attach_via_bio_link(session):
    v = _nightclub(session, "Oficina Club", website="http://oficinaclub.com.br")

    def fake_search(name):
        return [SearchResult(username="oficina_club", full_name="Oficina Club",
                             is_verified=False, is_private=False)]

    def fake_profile(handle):
        return ProfileSignals(handle="oficina_club", bio_link="https://www.oficinaclub.com.br/",
                              category=None, bio_text=None, is_verified=False, follower_count=None)

    stats = discover(session, [v], search=fake_search, profile=fake_profile)

    assert v.instagram == "oficina_club"
    assert stats["attach"] == 1
    logs = session.query(VerificationLog).filter(VerificationLog.entity_id == v.id).all()
    assert len(logs) == 1
    assert "handle via ig_search" in logs[0].note


def test_discover_review_when_signals_weak(session):
    v = _nightclub(session, "Some Club", website="http://someclub.com.br")

    def fake_search(name):
        return [SearchResult(username="some_club_sp", full_name="Some Club SP",
                             is_verified=False, is_private=False)]

    def fake_profile(handle):
        return ProfileSignals(handle="some_club_sp", bio_link="https://linktr.ee/someclub",
                              category=None, bio_text=None, is_verified=False, follower_count=None)

    stats = discover(session, [v], search=fake_search, profile=fake_profile)

    assert not v.instagram
    assert stats["review"] == 1
    logs = session.query(VerificationLog).filter(VerificationLog.entity_id == v.id).all()
    assert len(logs) == 1
    assert "review" in logs[0].note


def test_discover_no_results(session):
    v = _nightclub(session, "Nowhere Club")

    stats = discover(session, [v], search=lambda name: [], profile=lambda h: None)

    assert not v.instagram
    assert stats["no_results"] == 1


def test_discover_isolates_failure_per_venue(session):
    v1 = _nightclub(session, "Broken Club")
    v2 = _nightclub(session, "Nowhere Club 2")

    def fake_search(name):
        if name == "Broken Club":
            raise RuntimeError("boom")
        return []

    stats = discover(session, [v1, v2], search=fake_search, profile=lambda h: None)

    assert stats["error"] == 1
    assert stats["no_results"] == 1     # v2 ainda foi processado apos a falha de v1
    log = session.query(VerificationLog).filter(VerificationLog.entity_id == v1.id).one()
    assert "erro" in log.note


def test_no_ig_venues_filters_and_orders_future_events_first(session):
    now = datetime.now(timezone.utc)
    no_event = _nightclub(session, "No Event Club")
    with_event = _nightclub(session, "Future Event Club")
    _nightclub(session, "Has IG Club", instagram="already")
    bar = Venue(name="Some Bar", category="bar", lat=-23.55, lng=-46.65, confidence=50)
    session.add(bar)
    session.add(Event(name="Festa", venue_id=with_event.id, status="scheduled",
                      starts_at=now + timedelta(days=1)))
    session.flush()

    result = no_ig_venues(session)

    assert [v.id for v in result] == [with_event.id, no_event.id]
