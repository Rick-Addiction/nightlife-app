# tests/test_api.py
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from nightlife.api.deps import get_session
from nightlife.api.main import app
from nightlife.models import Event, Venue

SP = ZoneInfo("America/Sao_Paulo")


def _client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def test_list_and_get_venue(session):
    v = Venue(name="Lab Club", category="nightclub", lat=-23.561, lng=-46.656,
              status="operational", confidence=70, is_monitored=True)
    session.add(v)
    session.flush()
    client = _client(session)
    try:
        r = client.get("/venues", params={"min_confidence": 50})
        assert r.status_code == 200
        assert any(x["name"] == "Lab Club" for x in r.json())

        # min_confidence alto exclui
        r2 = client.get("/venues", params={"min_confidence": 90})
        assert all(x["name"] != "Lab Club" for x in r2.json())

        # filtro por type
        r3 = client.get("/venues", params={"type": "bar"})
        assert all(x["name"] != "Lab Club" for x in r3.json())

        rid = client.get(f"/venues/{v.id}")
        assert rid.status_code == 200 and rid.json()["name"] == "Lab Club"
        assert client.get("/venues/999999").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_list_events_filters_and_get(session):
    v = Venue(name="Audio", lat=-23.5, lng=-46.6, status="operational", confidence=60)
    session.add(v)
    session.flush()
    e = Event(name="Mamba Negra", starts_at=datetime(2099, 6, 13, 23, 0, tzinfo=SP),
              venue_id=v.id, status="scheduled", genre="techno", confidence=80)
    session.add(e)
    session.flush()
    client = _client(session)
    try:
        r = client.get("/events", params={"min_confidence": 50, "genre": "techno"})
        assert r.status_code == 200
        assert "Mamba Negra" in [x["name"] for x in r.json()]

        # genre diferente exclui
        r2 = client.get("/events", params={"genre": "forro"})
        assert "Mamba Negra" not in [x["name"] for x in r2.json()]

        # bbox que NAO contem o venue exclui o evento
        r3 = client.get("/events", params={"bbox": "10,10,11,11"})
        assert "Mamba Negra" not in [x["name"] for x in r3.json()]

        rid = client.get(f"/events/{e.id}")
        assert rid.status_code == 200 and rid.json()["venue_id"] == v.id
        assert client.get("/events/999999").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_events_date_range_filter(session):
    v = Venue(name="X", lat=-23.5, lng=-46.6, status="operational", confidence=50)
    session.add(v)
    session.flush()
    e1 = Event(name="Junho", starts_at=datetime(2099, 6, 15, 22, 0, tzinfo=SP),
               venue_id=v.id, status="scheduled", confidence=50)
    e2 = Event(name="Agosto", starts_at=datetime(2099, 8, 15, 22, 0, tzinfo=SP),
               venue_id=v.id, status="scheduled", confidence=50)
    session.add_all([e1, e2])
    session.flush()
    client = _client(session)
    try:
        r = client.get("/events", params={"date_from": "2099-07-01", "date_to": "2099-12-31"})
        names = [x["name"] for x in r.json()]
        assert "Agosto" in names and "Junho" not in names
    finally:
        app.dependency_overrides.clear()


def test_bbox_malformed_returns_400(session):
    client = _client(session)
    try:
        r = client.get("/venues", params={"bbox": "nao,eh,bbox"})
        assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()
