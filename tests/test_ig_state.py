from datetime import datetime, timedelta, timezone

from nightlife.models import Event, IgProfileState, Organizer, Venue
from nightlife.persistence.ig_state import (
    handles_to_scrape, get_or_create_state, record_success, record_failure,
    scrape_queue, record_venue_activity,
)


def test_handles_to_scrape_so_venues_relevant(session):
    session.add_all([
        Venue(name="Club A", instagram="a", category="nightclub"),        # relevant
        Venue(name="Espaco B", instagram="b", is_monitored=True),         # relevant (monitorado)
        Venue(name="Dormente D", instagram="d", category="events_venue"), # dormant -> fora
        Venue(name="Buffet E", instagram="e", category="events_venue"),   # blocked -> fora
        Organizer(name="C", instagram="c"),                               # organizer entra
        Organizer(name="Plataforma", instagram="sympla"),                 # platform -> fora
    ])
    session.flush()
    assert handles_to_scrape(session) == ["a", "b", "c"]


def test_handles_to_scrape_venue_com_evento_vira_relevant(session):
    v = Venue(name="Espaco F", instagram="f", category="events_venue")    # sem evento = dormant
    session.add(v)
    session.flush()
    assert handles_to_scrape(session) == []
    session.add(Event(name="Festa", venue_id=v.id, status="scheduled"))   # agora tem evento
    session.flush()
    assert handles_to_scrape(session) == ["f"]                            # promovido a relevant


def test_handles_to_scrape_ignora_pausados(session):
    session.add(Venue(name="A", instagram="a", category="nightclub"))     # relevant
    session.add(IgProfileState(handle="a", consecutive_failures=3))
    session.flush()
    assert handles_to_scrape(session, pause_threshold=3) == []
    assert handles_to_scrape(session, pause_threshold=4) == ["a"]


def test_cursor_success_e_failure(session):
    st = get_or_create_state(session, "a")
    assert st.consecutive_failures == 0
    record_failure(st)
    record_failure(st)
    assert st.consecutive_failures == 2
    record_success(st, "SHORT123")
    assert st.consecutive_failures == 0
    assert st.last_shortcode == "SHORT123"
    assert st.last_scraped_at is not None


def _v(session, name, handle, **kw):
    v = Venue(name=name, instagram=handle, category="nightclub", **kw)
    session.add(v)
    session.flush()
    return v


def _state(session, handle, days_ago):
    st = IgProfileState(handle=handle)
    if days_ago is not None:
        st.last_scraped_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    session.add(st)
    session.flush()
    return st


def test_scrape_queue_quentes_primeiro_com_cota(session):
    futuro = datetime.now(timezone.utc) + timedelta(days=3)
    # 3 quentes (evento futuro/monitorado) + 3 frios; cap 4 -> ceil(4*0.7)=3 quentes + 1 frio
    for i, h in enumerate(["hot1", "hot2"]):
        v = _v(session, f"Hot {i}", h)
        session.add(Event(name="F", venue_id=v.id, starts_at=futuro))
    _v(session, "Hot Mon", "hot3", is_monitored=True)
    for i, h in enumerate(["cold1", "cold2", "cold3"]):
        _v(session, f"Cold {i}", h)
    session.flush()
    q = scrape_queue(session, cap=4)
    assert set(q[:3]) == {"hot1", "hot2", "hot3"}   # quentes na frente
    assert len(q) == 4 and q[3].startswith("cold")  # 1 vaga sobrou pro frio


def test_scrape_queue_antiguidade_dentro_do_nivel(session):
    for h in ["a", "b", "c"]:
        _v(session, h.upper(), h)
    _state(session, "a", days_ago=1)     # varrido ontem
    _state(session, "b", days_ago=30)    # varrido ha 1 mes
    # "c" nunca varrido (sem state)
    session.flush()
    q = scrape_queue(session, cap=3)
    assert q == ["c", "b", "a"]          # nunca-varrido primeiro, depois o mais antigo


def test_scrape_queue_quentes_excedentes_completam_vagas(session):
    futuro = datetime.now(timezone.utc) + timedelta(days=3)
    for i in range(4):                    # 4 quentes, 0 frios; cap 4
        v = _v(session, f"H{i}", f"hot{i}")
        session.add(Event(name="F", venue_id=v.id, starts_at=futuro))
    session.flush()
    q = scrape_queue(session, cap=4)
    assert len(q) == 4                    # cota nao desperdica vaga quando nao ha frio


def test_scrape_queue_organizer_com_evento_futuro_e_quente(session):
    futuro = datetime.now(timezone.utc) + timedelta(days=3)
    org = Organizer(name="Mamba", instagram="mambaorg")
    session.add(org)
    session.flush()
    session.add(Event(name="F", organizer_id=org.id, starts_at=futuro))
    _v(session, "Frio", "frio1")
    session.flush()
    q = scrape_queue(session, cap=1)
    assert q == ["mambaorg"]              # organizer quente fura a fila


def test_scrape_queue_respeita_pausados(session):
    _v(session, "A", "a")
    session.add(IgProfileState(handle="a", consecutive_failures=3))
    session.flush()
    assert scrape_queue(session, cap=5, pause_threshold=3) == []


def test_record_venue_activity_grava_no_dono_do_handle(session):
    v = _v(session, "Selva", "selva.011")
    ts = datetime(2026, 7, 1, tzinfo=timezone.utc)
    record_venue_activity(session, "selva.011", ts)
    assert v.ig_last_post_at == ts
    record_venue_activity(session, "handle_de_organizer", ts)   # nao explode, nao toca venue
    record_venue_activity(session, "selva.011", None)           # None nao apaga
    assert v.ig_last_post_at == ts


def test_handles_in_area_filtra_por_raio_e_ordena_por_antiguidade(session):
    from datetime import datetime, timezone
    from nightlife.persistence.ig_state import get_or_create_state, handles_in_area
    from nightlife.models import Venue
    dentro_novo = Venue(name="Blitz Haus", instagram="blitzhaus", lat=-23.552, lng=-46.652, confidence=50)
    dentro_velho = Venue(name="Netao", instagram="netao", lat=-23.5517, lng=-46.6516, confidence=50)
    fora = Venue(name="D-Edge", instagram="dedge", lat=-23.5207, lng=-46.6663, confidence=50)
    sem_geo = Venue(name="Fantasma", instagram="fantasma", confidence=50)
    buffet = Venue(name="Buffet Alegria Kids", instagram="alegriakids", lat=-23.552, lng=-46.653, confidence=50)
    session.add_all([dentro_novo, dentro_velho, fora, sem_geo, buffet])
    session.flush()
    st = get_or_create_state(session, "netao")
    st.last_scraped_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    session.flush()

    out = handles_in_area(session, -23.553, -46.656, 2.0)

    # nunca-varrido primeiro, depois o mais antigo; fora do raio/sem geo/buffet ficam fora
    assert out == ["blitzhaus", "netao"]


def test_handles_in_area_exclui_pausados(session):
    from nightlife.persistence.ig_state import get_or_create_state, handles_in_area
    from nightlife.models import Venue
    v = Venue(name="Pausado Club", instagram="pausado", lat=-23.553, lng=-46.656, confidence=50)
    session.add(v)
    session.flush()
    st = get_or_create_state(session, "pausado")
    st.consecutive_failures = 3
    session.flush()
    assert handles_in_area(session, -23.553, -46.656, 2.0) == []


def test_follow_queue_nao_seguidos_quentes_primeiro_e_cap(session):
    from datetime import datetime, timezone
    from nightlife.persistence.ig_state import follow_queue, get_or_create_state
    from nightlife.models import Event, Venue
    quente = Venue(name="Blitz Haus", instagram="blitzhaus", lat=-23.55, lng=-46.65,
                   confidence=50)
    frio = Venue(name="Bar X", instagram="barx", lat=-23.55, lng=-46.65, confidence=50)
    ja_seg = Venue(name="Seguido", instagram="jaseg", lat=-23.55, lng=-46.65, confidence=50)
    session.add_all([quente, frio, ja_seg])
    session.flush()
    # quente tem evento futuro
    session.add(Event(name="Festa", status="scheduled", confidence=50, venue_id=quente.id,
                      starts_at=datetime(2099, 1, 1, tzinfo=timezone.utc)))
    st = get_or_create_state(session, "jaseg")
    st.followed_at = datetime.now(timezone.utc)   # ja seguido -> fora da fila
    session.flush()

    fila = follow_queue(session, cap=10)

    assert "jaseg" not in fila
    assert fila[0] == "blitzhaus"          # quente primeiro
    assert set(fila) == {"blitzhaus", "barx"}


def test_follow_queue_respeita_cap(session):
    from nightlife.persistence.ig_state import follow_queue
    from nightlife.models import Venue
    for i in range(5):
        session.add(Venue(name=f"V{i}", instagram=f"v{i}", lat=-23.55, lng=-46.65, confidence=50))
    session.flush()
    assert len(follow_queue(session, cap=3)) == 3
