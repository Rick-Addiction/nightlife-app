# tests/test_organizers.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nightlife.models import Organizer, Venue
from nightlife.persistence.events_repo import upsert_event
from nightlife.persistence.inputs import EventInput, SourceInfo
from nightlife.persistence.organizers import get_or_create_organizer

SP = ZoneInfo("America/Sao_Paulo")
REF = date(2026, 6, 1)


def test_get_or_create_reuses_by_normalized_name(session):
    a = get_or_create_organizer(session, "Mamba Org")
    b = get_or_create_organizer(session, "mamba org")
    assert a.id == b.id
    assert len(session.scalars(select(Organizer)).all()) == 1


def test_event_links_and_gapfills_organizer(session):
    v = Venue(name="Lab Club")
    session.add(v)
    session.flush()
    org = get_or_create_organizer(session, "Mamba Org")

    e = upsert_event(
        session,
        EventInput(name="Mamba Negra", starts_at=datetime(2026, 6, 13, 23, 0, tzinfo=SP),
                   venue_id=v.id, venue_name=v.name, organizer="Mamba Org", organizer_id=org.id),
        SourceInfo(source_type="ticketing", source_url="http://t", raw_payload="p", extracted_fields={}),
        reference=REF,
    )
    assert e.organizer_id == org.id

    # merge vindo de outra fonte SEM organizer_id nao apaga o link (gap-fill)
    e2 = upsert_event(
        session,
        EventInput(name="MAMBA NEGRA", starts_at=datetime(2026, 6, 13, 23, 30, tzinfo=SP),
                   venue_id=v.id, venue_name=v.name),
        SourceInfo(source_type="instagram", source_url="http://ig", raw_payload="p", extracted_fields={}),
        reference=REF,
    )
    assert e2.id == e.id and e2.organizer_id == org.id
