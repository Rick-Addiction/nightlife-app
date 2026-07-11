from datetime import datetime, timezone

from fastapi.testclient import TestClient

from nightlife.api.deps import get_session
from nightlife.api.main import app
from nightlife.models import AreaSweep


def _client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def test_post_cria_sweep_e_spawna_subprocesso(session, monkeypatch):
    spawned = {}

    def _fake_spawn(sweep_id):
        # nota: "spawned.setdefault(...) or 4242" do plano original sempre
        # retorna sweep_id (truthy, ids comecam em 1) -- corrigido pra
        # capturar o id passado E devolver o pid fixo de teste.
        spawned["id"] = sweep_id
        return 4242

    monkeypatch.setattr("nightlife.api.main._spawn_sweep", _fake_spawn)
    client = _client(session)
    try:
        r = client.post("/admin/area-sweeps", json={"lat": -23.553, "lng": -46.656, "km": 2.0})
        assert r.status_code == 202
        sweep_id = r.json()["id"]
        assert spawned["id"] == sweep_id
        sw = session.get(AreaSweep, sweep_id)
        assert sw.status == "running"
        assert sw.pid == 4242
    finally:
        app.dependency_overrides.clear()


def test_post_409_se_ja_ha_running(session, monkeypatch):
    monkeypatch.setattr("nightlife.api.main._spawn_sweep", lambda sweep_id: 1)
    session.add(AreaSweep(center_lat=-23.5, center_lng=-46.6, radius_km=2,
                          status="running", started_at=datetime.now(timezone.utc)))
    session.flush()
    client = _client(session)
    try:
        r = client.post("/admin/area-sweeps", json={"lat": -23.5, "lng": -46.6, "km": 1.0})
        assert r.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_get_current_devolve_ultimo_com_report_e_diff(session):
    session.add(AreaSweep(center_lat=-23.5, center_lng=-46.6, radius_km=2, status="done",
                          phase="done", total_handles=2,
                          started_at=datetime.now(timezone.utc),
                          report=[{"handle": "aura", "status": "ok", "posts_novos": 1,
                                   "flyers": ["SC1"], "festas": [], "venue_id": 1,
                                   "venue_name": "Aura"}],
                          diff={"novas_festas": 1, "venues_com_pin_novo": ["Aura"]}))
    session.flush()
    client = _client(session)
    try:
        r = client.get("/admin/area-sweeps/current")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "done"
        assert body["diff"]["novas_festas"] == 1
        assert body["report"][0]["handle"] == "aura"
        assert body["done_handles"] == 1
    finally:
        app.dependency_overrides.clear()


def test_get_current_404_sem_nenhum(session):
    client = _client(session)
    try:
        assert client.get("/admin/area-sweeps/current").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_post_spawn_falhando_marca_error_e_devolve_500(session, monkeypatch):
    def _boom(sweep_id):
        raise OSError("interpreter sumiu")
    monkeypatch.setattr("nightlife.api.main._spawn_sweep", _boom)
    client = _client(session)
    try:
        r = client.post("/admin/area-sweeps", json={"lat": -23.5, "lng": -46.6, "km": 2.0})
        assert r.status_code == 500
        sw = session.scalars(
            __import__("sqlalchemy").select(AreaSweep).order_by(AreaSweep.id.desc())
        ).first()
        assert sw.status == "error"
        assert "spawn" in (sw.error or "")
        assert sw.finished_at is not None
        # lock liberado: um POST novo funciona
        monkeypatch.setattr("nightlife.api.main._spawn_sweep", lambda sweep_id: 77)
        assert client.post("/admin/area-sweeps",
                           json={"lat": -23.5, "lng": -46.6, "km": 2.0}).status_code == 202
    finally:
        app.dependency_overrides.clear()
