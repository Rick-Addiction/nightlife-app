# tests/test_events_repo.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nightlife.models import DedupeCandidate, Event, EventSource, Venue
from nightlife.persistence.inputs import EventInput, SourceInfo
from nightlife.persistence.events_repo import upsert_event

SP = ZoneInfo("America/Sao_Paulo")
REF = date(2026, 6, 1)


def _venue(session, name="Lab Club"):
    v = Venue(name=name)
    session.add(v)
    session.flush()
    return v


def _src(stype="ticketing", url="http://t"):
    return SourceInfo(source_type=stype, source_url=url, raw_payload="p", extracted_fields={})


def _evin(name, dt, venue, ticket=None):
    return EventInput(name=name, starts_at=dt, venue_id=venue.id, venue_name=venue.name, ticket_url=ticket)


def test_creates_event_with_score_and_source(session):
    v = _venue(session)
    e = upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v),
                     _src(), reference=REF)
    assert e.id is not None
    assert e.confidence == 20 + 20 + 25  # future + venue + ticketing
    assert len(session.scalars(select(EventSource)).all()) == 1


def test_duplicate_merges_and_multisource_bonus_fires(session):
    v = _venue(session)
    upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v),
                 _src("ticketing", "http://t"), reference=REF)
    e = upsert_event(session, _evin("MAMBA NEGRA", datetime(2026, 6, 13, 23, 30, tzinfo=SP), v),
                     _src("instagram", "http://ig"), reference=REF)
    assert len(session.scalars(select(Event)).all()) == 1       # merge
    assert len(session.scalars(select(EventSource)).all()) == 2  # duas evidencias
    # 2 source_types distintos -> +20 multi-fonte (spec §7, antes morto)
    assert e.confidence == 20 + 20 + 25 + 20


def test_distinct_events_create_two(session):
    v1 = _venue(session, "Lab Club")
    v2 = _venue(session, "Cargo")
    upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v1),
                 _src(), reference=REF)
    upsert_event(session, _evin("Gop Tun", datetime(2026, 7, 20, 16, 0, tzinfo=SP), v2),
                 _src(url="http://t2"), reference=REF)
    assert len(session.scalars(select(Event)).all()) == 2


def test_medium_confidence_creates_dedupe_candidate(session):
    v = _venue(session)
    upsert_event(session, _evin("Festa X", datetime(2026, 6, 13, 22, 0, tzinfo=SP), v),
                 _src(), reference=REF)
    upsert_event(session, _evin("Festa X", datetime(2026, 6, 14, 14, 0, tzinfo=SP), v),
                 _src("instagram", "http://ig"), reference=REF)
    assert len(session.scalars(select(Event)).all()) == 2
    cands = session.scalars(select(DedupeCandidate)).all()
    assert len(cands) == 1 and cands[0].decision == "review" and cands[0].kind == "event"


def test_linked_venue_gains_future_event_bonus(session):
    v = _venue(session)
    assert v.confidence == 0
    upsert_event(session, _evin("Mamba Negra", datetime(2026, 6, 13, 23, 0, tzinfo=SP), v),
                 _src(), reference=REF)
    # o upsert do evento recomputa o venue linkado: +15 future_event_linked
    assert v.confidence == 15
