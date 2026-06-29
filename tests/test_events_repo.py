# tests/test_events_repo.py
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nightlife.models import Venue, Event, EventSource, DedupeCandidate
from nightlife.domain.scoring import EventSignals
from nightlife.persistence.inputs import EventInput, SourceInfo
from nightlife.persistence.events_repo import upsert_event

SP = ZoneInfo("America/Sao_Paulo")


def _venue(session, name="Lab Club"):
    v = Venue(name=name)
    session.add(v)
    session.flush()
    return v


def _src(stype="ticketing"):
    return SourceInfo(source_type=stype, source_url="http://t", raw_payload="p", extracted_fields={})


def _evin(name, dt, venue, ticket=None):
    # liga o evento a um venue real: o dedupe usa o nome do venue na comparacao
    return EventInput(name=name, starts_at=dt, venue_id=venue.id, venue_name=venue.name, ticket_url=ticket)


def test_creates_event_with_score_and_source(session):
    v = _venue(session)
    e = upsert_event(
        session,
        _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v),
        _src(),
        EventSignals(future_date=True, venue_matched=True, ticketing_source=True),
    )
    session.flush()
    assert e.id is not None
    assert e.confidence == 20 + 20 + 25
    assert len(session.scalars(select(EventSource)).all()) == 1


def test_duplicate_event_auto_merges(session):
    v = _venue(session)
    upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v),
                 _src(), EventSignals(future_date=True))
    session.flush()
    upsert_event(session, _evin("MAMBA NEGRA", datetime(2026, 6, 13, 23, 30, tzinfo=SP), v),
                 _src("instagram"), EventSignals(future_date=True))
    session.flush()
    assert len(session.scalars(select(Event)).all()) == 1
    assert len(session.scalars(select(EventSource)).all()) == 2


def test_distinct_events_create_two(session):
    v1 = _venue(session, "Lab Club")
    v2 = _venue(session, "Cargo")
    upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v1),
                 _src(), EventSignals(future_date=True))
    upsert_event(session, _evin("Gop Tun", datetime(2026, 7, 20, 16, 0, tzinfo=SP), v2),
                 _src(), EventSignals(future_date=True))
    session.flush()
    assert len(session.scalars(select(Event)).all()) == 2


def test_medium_confidence_creates_dedupe_candidate(session):
    v = _venue(session)
    # mesmo nome e venue, ~16h de diferenca => "review" (score ~0.82: nao auto-merge, nao distinct)
    upsert_event(session, _evin("Festa X", datetime(2026, 6, 13, 22, 0, tzinfo=SP), v),
                 _src(), EventSignals(future_date=True))
    session.flush()
    upsert_event(session, _evin("Festa X", datetime(2026, 6, 14, 14, 0, tzinfo=SP), v),
                 _src("instagram"), EventSignals(future_date=True))
    session.flush()
    assert len(session.scalars(select(Event)).all()) == 2
    cands = session.scalars(select(DedupeCandidate)).all()
    assert len(cands) == 1 and cands[0].decision == "review"
