# tests/test_pipeline.py
from datetime import date

from sqlalchemy import select

from nightlife.models import Venue, Event, IngestionRun
from nightlife.ingestion.base import RawVenue, RawEventPage
from nightlife.ingestion.mock_source import MockSource
from nightlife.ingestion.pipeline import run_ingestion

REF = date(2026, 6, 1)

JSONLD = (
    '<script type="application/ld+json">'
    '{"@type":"Event","name":"Mamba Negra","startDate":"2099-06-13T23:00:00-03:00",'
    '"location":{"name":"Lab Club"},"offers":{"url":"https://t/x"}}</script>'
)


def test_pipeline_creates_venue_event_and_run(session):
    src = MockSource(
        [RawVenue(name="Lab Club", source_type="google_places", lat=-23.561, lng=-46.656)],
        [RawEventPage(kind="jsonld", content=JSONLD, source_type="ticketing", source_url="https://t/x")],
    )
    run = run_ingestion(session, src, reference=REF)
    session.flush()

    assert run.status == "finished"
    assert run.records_found == 2  # 1 venue + 1 pagina

    venues = session.scalars(select(Venue)).all()
    # google_places(30) + future_event_linked(15): o evento ingerido na mesma
    # rodada recomputa o venue linkado
    assert len(venues) == 1 and venues[0].confidence == 45

    events = session.scalars(select(Event)).all()
    assert len(events) == 1
    e = events[0]
    assert e.name == "Mamba Negra"
    assert e.venue_id == venues[0].id                      # resolveu "Lab Club"
    assert e.confidence == 20 + 20 + 25                    # future + venue_matched + ticketing

    runs = session.scalars(select(IngestionRun)).all()
    assert len(runs) == 1 and runs[0].finished_at is not None


def test_pipeline_event_without_resolvable_venue(session):
    # freetext nao extrai venue -> evento fica sem venue e marcado no_venue
    flyer = "GOP TUN\n20/07 16h\nhttps://shotgun.live/x"
    src = MockSource([], [RawEventPage(kind="freetext", content=flyer, source_type="instagram")])
    run = run_ingestion(session, src, reference=REF)
    session.flush()
    events = session.scalars(select(Event)).all()
    assert len(events) == 1
    assert events[0].venue_id is None
    assert run.records_created == 1
    # sem venue e sem ticketing: future(20) - no_venue(20) = 0
    assert events[0].confidence == 0


class _BoomSource:
    def venues(self):
        raise RuntimeError("overpass caiu")

    def event_pages(self):
        return []


def test_pipeline_source_fetch_failure_marks_run_error(session):
    # falha da fonte inteira (rede/parse) marca o run com erro em vez de estourar
    run = run_ingestion(session, _BoomSource(), reference=REF, label="osm")
    session.flush()
    assert run.status == "error"
    assert "overpass caiu" in run.errors
    assert run.finished_at is not None


def test_pipeline_multi_event_page_counts_each_event(session):
    # uma pagina jsonld com 2 eventos: found conta 1 pagina, created conta 2 eventos
    two = (
        '<script type="application/ld+json">'
        '[{"@type":"Event","name":"Festa A","startDate":"2099-06-13T23:00:00-03:00"},'
        '{"@type":"Event","name":"Festa B","startDate":"2099-06-20T23:00:00-03:00"}]'
        "</script>"
    )
    src = MockSource([], [RawEventPage(kind="jsonld", content=two, source_type="ticketing")])
    run = run_ingestion(session, src, reference=REF)
    session.flush()
    assert run.records_found == 1       # 1 pagina
    assert run.records_created == 2     # 2 eventos
    assert len(session.scalars(select(Event)).all()) == 2
