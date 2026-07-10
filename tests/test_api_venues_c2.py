# tests/test_api_venues_c2.py
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from nightlife.api.deps import get_session
from nightlife.api.main import app
from nightlife.models import Venue, VenueSource


def _client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def test_ig_last_post_at_exposto(session):
    v = Venue(name="Selva Club", lat=-23.55, lng=-46.65, confidence=50,
              ig_last_post_at=datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc))
    session.add(v)
    session.flush()
    client = _client(session)
    try:
        row = next(x for x in client.get("/venues?include_all=true").json() if x["id"] == v.id)
        assert row["ig_last_post_at"] is not None
        assert row["ig_last_post_at"].startswith("2026-07-09")
        one = client.get(f"/venues/{v.id}").json()
        assert one["ig_last_post_at"].startswith("2026-07-09")
    finally:
        app.dependency_overrides.clear()


def test_places_verified_por_evidencia_google_places(session):
    com = Venue(name="D-Edge", lat=-23.52, lng=-46.66, confidence=50)
    sem = Venue(name="Bar Aleatorio", lat=-23.56, lng=-46.64, confidence=50)
    session.add_all([com, sem])
    session.flush()
    session.add(VenueSource(venue_id=com.id, source_type="google_places",
                            source_url="place:ChIJfake123"))
    session.flush()
    client = _client(session)
    try:
        rows = {x["id"]: x for x in client.get("/venues?include_all=true").json()}
        assert rows[com.id]["places_verified"] is True
        assert rows[sem.id]["places_verified"] is False
        assert client.get(f"/venues/{com.id}").json()["places_verified"] is True
        assert client.get(f"/venues/{sem.id}").json()["places_verified"] is False
    finally:
        app.dependency_overrides.clear()
