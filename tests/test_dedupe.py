# tests/test_dedupe.py
from datetime import datetime
from zoneinfo import ZoneInfo

from nightlife.domain.dedupe import EventKey, dedupe_score, classify, compare

SP = ZoneInfo("America/Sao_Paulo")


def _ev(name, dt, venue=None, organizer=None, ticket=None):
    return EventKey(name=name, starts_at=dt, venue_name=venue, organizer=organizer, ticket_url=ticket)


def test_same_event_auto_merges():
    a = _ev("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), venue="Lab Club")
    b = _ev("MAMBA NEGRA", datetime(2026, 6, 13, 23, 30, tzinfo=SP), venue="lab club")
    assert classify(dedupe_score(a, b)) == "auto_merge"


def test_same_ticket_url_forces_auto_merge():
    a = _ev("Festa X", datetime(2026, 6, 13, 23, 0, tzinfo=SP), ticket="https://sympla.com.br/e/123")
    b = _ev("Evento Y", datetime(2026, 6, 13, 22, 0, tzinfo=SP), ticket="https://sympla.com.br/e/123")
    assert classify(dedupe_score(a, b)) == "auto_merge"


def test_distinct_events():
    a = _ev("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), venue="Lab Club")
    b = _ev("Carlos Capslock", datetime(2026, 7, 20, 23, 0, tzinfo=SP), venue="Audio")
    assert classify(dedupe_score(a, b)) == "distinct"


def test_recurring_party_same_name_far_dates_is_distinct():
    a = _ev("Gop Tun", datetime(2026, 6, 7, 16, 0, tzinfo=SP), venue="Cargo")
    b = _ev("Gop Tun", datetime(2026, 6, 14, 16, 0, tzinfo=SP), venue="Cargo")  # +7 dias
    assert classify(dedupe_score(a, b)) == "distinct"


def test_compare_returns_result_object():
    a = _ev("Festa", datetime(2026, 6, 13, 23, 0, tzinfo=SP), venue="Lab")
    b = _ev("Festa", datetime(2026, 6, 13, 23, 0, tzinfo=SP), venue="Lab")
    r = compare(a, b)
    assert r.decision == "auto_merge" and r.score >= 0.9
