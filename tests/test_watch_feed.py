from datetime import time as dtime

from nightlife.ingestion.feed_source import FeedItem
from nightlife.models import IgProfileState, Venue
from nightlife.watch_feed import detect_and_fetch, in_window


def test_in_window_janela_noturna():
    assert in_window(dtime(11, 0), start=10, end=2) is True
    assert in_window(dtime(1, 0), start=10, end=2) is True      # madrugada ate 02h
    assert in_window(dtime(5, 0), start=10, end=2) is False


def test_detect_and_fetch_baixa_novos_e_atualiza_cursor(session):
    v = Venue(name="Selva", instagram="selva.011", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    items = [FeedItem("selva.011", "SC2", 200), FeedItem("selva.011", "SC1", 100)]
    baixados = []

    n = detect_and_fetch(
        session, items,
        fetch=lambda handle, shortcode: baixados.append((handle, shortcode)),
        cursor_by_handle={"selva.011": "SC1"})

    assert baixados == [("selva.011", "SC2")]           # so o novo
    assert n == 1
    st = session.query(IgProfileState).filter_by(handle="selva.011").one()
    assert st.last_shortcode == "SC2"                   # cursor avancou pro topo


def test_detect_and_fetch_sem_novos_e_noop(session):
    v = Venue(name="Selva", instagram="selva.011", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    items = [FeedItem("selva.011", "SC1", 100)]
    n = detect_and_fetch(session, items, fetch=lambda h, s: None,
                         cursor_by_handle={"selva.011": "SC1"})
    assert n == 0
