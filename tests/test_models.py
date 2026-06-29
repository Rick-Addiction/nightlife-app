# tests/test_models.py
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nightlife.models import Venue, VenueSource, Event, EventSource, IngestionRun

SP = ZoneInfo("America/Sao_Paulo")


def test_create_and_read_venue_with_source(session):
    v = Venue(name="Lab Club", category="nightclub", lat=-23.561, lng=-46.656,
              status="operational", confidence=70, is_monitored=True)
    session.add(v)
    session.flush()
    session.add(VenueSource(
        venue_id=v.id, source_type="google_places", source_url="http://x",
        raw_payload_hash="abc", extracted_fields={"name": "Lab Club"},
        confidence_contribution=30,
    ))
    session.flush()

    got = session.scalars(select(Venue).where(Venue.name == "Lab Club")).one()
    assert got.confidence == 70
    assert got.is_monitored is True
    assert len(got.sources) == 1
    assert got.sources[0].extracted_fields["name"] == "Lab Club"


def test_create_event_with_venue_and_source(session):
    v = Venue(name="Audio", lat=-23.5, lng=-46.6)
    session.add(v)
    session.flush()
    e = Event(name="Mamba Negra", starts_at=datetime(2026, 6, 13, 23, 0, tzinfo=SP),
              venue_id=v.id, status="scheduled", confidence=85,
              lineup_text="DJ A, DJ B", ticket_url="http://t")
    session.add(e)
    session.flush()
    session.add(EventSource(
        event_id=e.id, source_type="ticketing", source_url="http://t",
        raw_payload_hash="z", extracted_fields={}, confidence_contribution=25,
    ))
    session.flush()
    assert e.venue.name == "Audio"
    assert len(e.sources) == 1


def test_ingestion_run_row(session):
    run = IngestionRun(source="mock", status="finished",
                       records_found=3, records_created=2, records_updated=1)
    session.add(run)
    session.flush()
    assert run.id is not None
    assert run.records_found == 3
