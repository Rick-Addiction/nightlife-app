# tests/test_scoring.py
from nightlife.domain.scoring import (
    VenueSignals, EventSignals, score_venue, score_event,
)


def test_venue_all_positive():
    s = VenueSignals(
        google_places_operational=True, osm_match=True, official_website=True,
        instagram_link=True, future_event_linked=True,
    )
    assert score_venue(s) == 30 + 20 + 20 + 15 + 15


def test_venue_individual_bonuses():
    assert score_venue(VenueSignals(google_places_operational=True)) == 30
    assert score_venue(VenueSignals(osm_match=True)) == 20
    assert score_venue(VenueSignals(official_website=True)) == 20
    assert score_venue(VenueSignals(instagram_link=True)) == 15
    assert score_venue(VenueSignals(future_event_linked=True)) == 15


def test_venue_penalties_and_clamp():
    s = VenueSignals(google_places_operational=True, permanently_closed=True)
    assert score_venue(s) == max(0, 30 - 50)  # clamp em 0
    assert score_venue(VenueSignals(unverified=True)) == 0


def test_event_all_positive():
    s = EventSignals(
        future_date=True, venue_matched=True, official_source=True,
        ticketing_source=True, independent_source_count=2,
    )
    assert score_event(s) == 20 + 20 + 25 + 25 + 20


def test_event_single_source_no_multisource_bonus():
    s = EventSignals(future_date=True, independent_source_count=1)
    assert score_event(s) == 20


def test_event_penalties_and_clamp():
    s = EventSignals(future_date=True, cancelled=True)
    assert score_event(s) == max(0, 20 - 50)
    assert score_event(EventSignals(past_date=True)) == 0
