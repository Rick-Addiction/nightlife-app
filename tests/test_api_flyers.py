# tests/test_api_flyers.py
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from nightlife import config
from nightlife.api.deps import get_session
from nightlife.api.main import app
from nightlife.models import Event, EventSource, Venue

SP = ZoneInfo("America/Sao_Paulo")


def _client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def _event_with_permalink(session, shortcode):
    v = Venue(name="Selva Club", lat=-23.55, lng=-46.65)
    session.add(v)
    session.flush()
    e = Event(name="Mamba Negra", venue_id=v.id, status="scheduled", confidence=50,
              starts_at=datetime(2099, 7, 12, 23, 0, tzinfo=SP))
    session.add(e)
    session.flush()
    session.add(EventSource(event_id=e.id, source_type="vision_flyer",
                            source_url=f"https://www.instagram.com/p/{shortcode}/"))
    session.flush()
    return e


def test_flyer_url_quando_arquivo_existe(session, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FLYERS_PROCESSED_DIR", tmp_path)
    (tmp_path / "ABC12345678.jpg").write_bytes(b"x")
    e = _event_with_permalink(session, "ABC12345678")
    client = _client(session)
    try:
        row = next(x for x in client.get("/events").json() if x["id"] == e.id)
        assert row["flyer_url"] == "/flyers/ABC12345678.jpg"
        one = client.get(f"/events/{e.id}").json()
        assert one["flyer_url"] == "/flyers/ABC12345678.jpg"
    finally:
        app.dependency_overrides.clear()


def test_flyer_url_extensao_variada_e_ausencia(session, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FLYERS_PROCESSED_DIR", tmp_path)
    (tmp_path / "WEBP1234567.webp").write_bytes(b"x")
    com = _event_with_permalink(session, "WEBP1234567")
    sem = _event_with_permalink(session, "NAOEXISTE11")
    client = _client(session)
    try:
        rows = {x["id"]: x for x in client.get("/events").json()}
        assert rows[com.id]["flyer_url"] == "/flyers/WEBP1234567.webp"
        assert rows[sem.id]["flyer_url"] is None
    finally:
        app.dependency_overrides.clear()


def test_evento_sem_source_ig_tem_flyer_null(session, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FLYERS_PROCESSED_DIR", tmp_path)
    v = Venue(name="X")
    session.add(v)
    session.flush()
    e = Event(name="Sem IG", venue_id=v.id, status="scheduled", confidence=10,
              starts_at=datetime(2099, 1, 1, 23, 0, tzinfo=SP))
    session.add(e)
    session.flush()
    client = _client(session)
    try:
        row = next(x for x in client.get("/events").json() if x["id"] == e.id)
        assert row["flyer_url"] is None
    finally:
        app.dependency_overrides.clear()
