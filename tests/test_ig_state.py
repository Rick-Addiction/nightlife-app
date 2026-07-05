from nightlife.models import Event, IgProfileState, Organizer, Venue
from nightlife.persistence.ig_state import (
    handles_to_scrape, get_or_create_state, record_success, record_failure,
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
