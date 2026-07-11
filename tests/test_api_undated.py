# tests/test_api_undated.py
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient

from nightlife.api.deps import get_session
from nightlife.api.main import app
from nightlife.models import Event, Venue


def _client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def _seed(session):
    v = Venue(name="Selva Club", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    fut = datetime.now(timezone.utc) + timedelta(days=7)
    session.add_all([
        Event(name="COM DATA", status="scheduled", confidence=50, venue_id=v.id, starts_at=fut),
        Event(name="SEM DATA", status="scheduled", confidence=50, venue_id=v.id, starts_at=None),
        Event(name="CANCELADA", status="cancelled", confidence=50, venue_id=v.id, starts_at=fut),
    ])
    session.flush()


def test_default_inclui_sem_data_no_fim_e_esconde_cancelada(session):
    _seed(session)
    client = _client(session)
    try:
        nomes = [e["name"] for e in client.get("/events").json()]
        assert "CANCELADA" not in nomes
        assert nomes.index("COM DATA") < nomes.index("SEM DATA")   # sem-data no fim
    finally:
        app.dependency_overrides.clear()


def test_janela_de_dia_especifico_exclui_sem_data(session):
    _seed(session)
    client = _client(session)
    try:
        hoje = datetime.now(timezone.utc).date().isoformat()
        nomes = [e["name"] for e in
                 client.get(f"/events?date_from={hoje}&date_to={hoje}").json()]
        assert "SEM DATA" not in nomes
    finally:
        app.dependency_overrides.clear()
