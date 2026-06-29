# tests/test_ingestion_signals.py
from nightlife.ingestion.signals import derive_venue_signals, derive_event_signals


def test_venue_signals_from_source_type():
    assert derive_venue_signals("google_places").google_places_operational is True
    assert derive_venue_signals("osm").osm_match is True
    assert derive_venue_signals("official_website").official_website is True
    assert derive_venue_signals("instagram").instagram_link is True
    # tipo desconhecido nao liga nenhum sinal
    s = derive_venue_signals("whatever")
    assert not any([s.google_places_operational, s.osm_match, s.official_website, s.instagram_link])


def test_event_signals_mapping():
    s = derive_event_signals(source_type="ticketing", has_future_date=True, venue_matched=True)
    assert s.future_date is True
    assert s.ticketing_source is True
    assert s.venue_matched is True
    assert s.no_venue is False

    s2 = derive_event_signals(source_type="official_website", has_future_date=False, venue_matched=False)
    assert s2.official_source is True
    assert s2.no_venue is True
    assert s2.ticketing_source is False
