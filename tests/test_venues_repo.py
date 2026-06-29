# tests/test_venues_repo.py
from sqlalchemy import select

from nightlife.models import Venue, VenueSource
from nightlife.domain.scoring import VenueSignals
from nightlife.persistence.inputs import VenueInput, SourceInfo
from nightlife.persistence.venues_repo import upsert_venue


def _src(stype="google_places"):
    return SourceInfo(source_type=stype, source_url="http://x",
                      raw_payload='{"k":1}', extracted_fields={"k": 1})


def test_creates_new_venue_with_score_and_source(session):
    v = upsert_venue(
        session,
        VenueInput(name="Lab Club", lat=-23.561, lng=-46.656, address="R. X", category="nightclub"),
        SourceInfo(source_type="google_places", source_url="http://g", raw_payload="p", extracted_fields={}),
        VenueSignals(google_places_operational=True, official_website=True),
    )
    session.flush()
    assert v.id is not None
    assert v.confidence == 30 + 20  # places + site
    rows = session.scalars(select(Venue)).all()
    assert len(rows) == 1
    srcs = session.scalars(select(VenueSource)).all()
    assert len(srcs) == 1 and srcs[0].confidence_contribution == v.confidence


def test_matching_reuses_existing_venue(session):
    upsert_venue(session, VenueInput(name="Lab Club", lat=-23.561, lng=-46.656),
                 _src(), VenueSignals(google_places_operational=True))
    session.flush()
    v2 = upsert_venue(session, VenueInput(name="lab club", lat=-23.5611, lng=-46.6561),
                      _src("osm"), VenueSignals(osm_match=True))
    session.flush()
    assert len(session.scalars(select(Venue)).all()) == 1      # nao duplicou
    assert len(session.scalars(select(VenueSource)).all()) == 2  # duas evidencias


def test_distinct_names_create_two_venues(session):
    upsert_venue(session, VenueInput(name="Lab Club"), _src(), VenueSignals())
    upsert_venue(session, VenueInput(name="Trackers"), _src(), VenueSignals())
    session.flush()
    assert len(session.scalars(select(Venue)).all()) == 2
