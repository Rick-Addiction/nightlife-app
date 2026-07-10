# tests/test_api.py
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from nightlife.api.deps import get_session
from nightlife.api.main import app
from nightlife.models import Event, Venue, VenueSource

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


def test_venues_sorted_by_effective_confidence_desc(session):
    a = Venue(name="Fraco", status="operational", confidence=30, category="nightclub", is_monitored=True)
    b = Venue(name="Forte", status="operational", confidence=80, category="nightclub", is_monitored=True)
    session.add_all([a, b])
    session.flush()
    client = _client(session)
    try:
        names = [x["name"] for x in client.get("/venues").json()]
        assert names.index("Forte") < names.index("Fraco")
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


def test_venues_esconde_dormant_e_buffet_por_padrao(session):
    session.add_all([
        Venue(name="Club Real", category="nightclub", status="operational", confidence=60, instagram="clubreal"),
        Venue(name="Espaco Dormente", category="events_venue", status="operational", confidence=60),
        Venue(name="Buffet Kids", category="events_venue", status="operational", confidence=60),
    ])
    session.flush()
    client = _client(session)
    try:
        names = [x["name"] for x in client.get("/venues").json()]
        assert names == ["Club Real"]                       # dormant e buffet escondidos
        all_names = [x["name"] for x in client.get("/venues", params={"include_all": "true"}).json()]
        assert set(all_names) == {"Club Real", "Espaco Dormente", "Buffet Kids"}
    finally:
        app.dependency_overrides.clear()


def test_venue_out_inclui_instagram_e_website(session):
    v = Venue(name="D-Edge", category="nightclub", lat=-23.53, lng=-46.66,
              status="operational", confidence=80, is_monitored=True,
              instagram="dedgeclub", website="https://d-edge.com.br")
    session.add(v)
    session.flush()
    client = _client(session)
    try:
        row = next(x for x in client.get("/venues").json() if x["name"] == "D-Edge")
        assert row["instagram"] == "dedgeclub"
        assert row["website"] == "https://d-edge.com.br"
    finally:
        app.dependency_overrides.clear()


def test_events_esconde_evento_de_venue_buffet(session):
    from datetime import datetime as _dt
    buf = Venue(name="Buffet Festas", status="operational", confidence=60)
    club = Venue(name="Club Z", category="nightclub", status="operational", confidence=60)
    session.add_all([buf, club]); session.flush()
    e_buf = Event(name="Aniversario", starts_at=_dt(2099, 6, 1, 22, tzinfo=SP),
                  venue_id=buf.id, status="scheduled", confidence=60)
    e_club = Event(name="Rave", starts_at=_dt(2099, 6, 1, 23, tzinfo=SP),
                   venue_id=club.id, status="scheduled", confidence=60)
    session.add_all([e_buf, e_club]); session.flush()
    client = _client(session)
    try:
        names = [x["name"] for x in client.get("/events").json()]
        assert "Rave" in names and "Aniversario" not in names   # evento de buffet escondido
        all_names = [x["name"] for x in client.get("/events", params={"include_all": "true"}).json()]
        assert "Aniversario" in all_names
    finally:
        app.dependency_overrides.clear()


def test_venues_v2_esconde_fantasma_e_mostra_verificado(session):
    fantasma = Venue(name="Fantasma RA", category="nightclub", lat=-23.5, lng=-46.6,
                     status="unverified", confidence=0)
    verificado = Venue(name="Selva Club", category="nightclub", lat=-23.55, lng=-46.65,
                       status="operational", confidence=30)
    session.add_all([fantasma, verificado])
    session.flush()
    session.add(VenueSource(venue_id=fantasma.id, source_type="ra", source_url="u1"))
    session.add(VenueSource(venue_id=verificado.id, source_type="google_places", source_url="P1"))
    session.flush()
    client = _client(session)
    try:
        names = [x["name"] for x in client.get("/venues").json()]
        assert "Selva Club" in names and "Fantasma RA" not in names
        all_names = [x["name"] for x in client.get("/venues", params={"include_all": "true"}).json()]
        assert "Fantasma RA" in all_names        # escape hatch preservado
    finally:
        app.dependency_overrides.clear()


def test_venues_ig_stale_esconde_so_contato(session):
    from datetime import timedelta, timezone as tz
    velho = datetime.now(tz.utc) - timedelta(days=400)
    parado = Venue(name="IG Parado", category="nightclub", lat=-23.5, lng=-46.6,
                   status="operational", confidence=30, instagram="parado",
                   ig_last_post_at=velho)
    vivo = Venue(name="IG Vivo", category="nightclub", lat=-23.5, lng=-46.6,
                 status="operational", confidence=30, instagram="vivo",
                 ig_last_post_at=datetime.now(tz.utc) - timedelta(days=10))
    session.add_all([parado, vivo])
    session.flush()
    client = _client(session)
    try:
        names = [x["name"] for x in client.get("/venues").json()]
        assert "IG Vivo" in names and "IG Parado" not in names
    finally:
        app.dependency_overrides.clear()


def test_events_dia_unico_inclui_noite_de_sp(session):
    # HOJE/AMANHA: date_from == date_to tem que pegar festa de 23h SP (que em
    # UTC ja e o dia seguinte) — comparar com meia-noite UTC dava janela ZERO
    v = Venue(name="Selva Club")
    session.add(v)
    session.flush()
    session.add(Event(name="Festa 23h", venue_id=v.id, status="scheduled", confidence=50,
                      starts_at=datetime(2099, 7, 12, 23, 0, tzinfo=SP)))
    session.add(Event(name="Madrugada 2h", venue_id=v.id, status="scheduled", confidence=50,
                      starts_at=datetime(2099, 7, 12, 2, 0, tzinfo=SP)))
    session.add(Event(name="Dia Seguinte", venue_id=v.id, status="scheduled", confidence=50,
                      starts_at=datetime(2099, 7, 13, 22, 0, tzinfo=SP)))
    session.flush()
    client = _client(session)
    try:
        names = [x["name"] for x in client.get(
            "/events", params={"date_from": "2099-07-12", "date_to": "2099-07-12"}).json()]
        assert "Festa 23h" in names and "Madrugada 2h" in names
        assert "Dia Seguinte" not in names
    finally:
        app.dependency_overrides.clear()
