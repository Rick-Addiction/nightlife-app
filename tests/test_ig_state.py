from nightlife.models import IgProfileState, Organizer, Venue
from nightlife.persistence.ig_state import (
    handles_to_scrape, get_or_create_state, record_success, record_failure,
)


def test_handles_to_scrape_uniao_venue_organizer(session):
    session.add_all([
        Venue(name="A", instagram="a"),
        Venue(name="B", instagram="b"),
        Venue(name="Sem IG"),
        Organizer(name="C", instagram="c"),
        Organizer(name="Dup", instagram="a"),  # duplicado com o venue A
    ])
    session.flush()
    assert handles_to_scrape(session) == ["a", "b", "c"]


def test_handles_to_scrape_ignora_pausados(session):
    session.add(Venue(name="A", instagram="a"))
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
