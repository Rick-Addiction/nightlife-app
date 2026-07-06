from datetime import date
from nightlife.ingestion.ra_source import parse_ra_events

# Shape real do eventListings do RA (capturado no probe; datas em 2099 = futuras).
RA_RESPONSE = {"data": {"eventListings": {"data": [
    {"event": {"id": "1", "title": "Fugaz recebe Guarizo",
               "date": "2099-07-08T00:00:00.000", "startTime": "2099-07-08T19:00:00.000",
               "contentUrl": "/events/1", "artists": [{"name": "Guarizo"}], "genres": [{"name": "House"}],
               "venue": {"id": "9", "name": "Fugaz Bar", "address": "Rua Cardeal Arcoverde, 1479",
                         "contentUrl": "/clubs/9"}}},
    {"event": {"id": "2", "title": "Baile Do Helipa",
               "date": "2099-07-08T00:00:00.000", "startTime": "2099-07-08T22:00:00.000",
               "contentUrl": "/events/2", "artists": [], "genres": [{"name": "Baile Funk"}],
               "venue": {"id": "8", "name": "TBA - Avenida X, 751", "address": None, "contentUrl": None}}},
    {"event": {"id": "3", "title": "",   # sem titulo -> descarta
               "date": "2099-07-08T00:00:00.000", "startTime": "2099-07-08T20:00:00.000",
               "contentUrl": "/events/3", "artists": [], "genres": [],
               "venue": {"id": "7", "name": "X", "address": None, "contentUrl": "/clubs/7"}}},
    {"event": {"id": "4", "title": "Evento Passado",   # passado -> descarta
               "date": "2000-01-01T00:00:00.000", "startTime": "2000-01-01T22:00:00.000",
               "contentUrl": "/events/4", "artists": [], "genres": [],
               "venue": {"id": "6", "name": "Velho", "address": None, "contentUrl": "/clubs/6"}}},
]}}}


def test_parse_ra_events():
    events = parse_ra_events(RA_RESPONSE, reference=date(2099, 1, 1))
    assert [e.name for e in events] == ["Fugaz recebe Guarizo", "Baile Do Helipa"]  # sem-titulo e passado fora

    fugaz = events[0]
    assert fugaz.source_type == "ra"
    assert fugaz.genre == "House"
    assert fugaz.lineup_text == "Guarizo"
    assert fugaz.source_url == "https://ra.co/events/1"
    assert fugaz.ticket_url == "https://ra.co/events/1"
    assert fugaz.venue is not None
    assert fugaz.venue.name == "Fugaz Bar"
    assert fugaz.venue.address == "Rua Cardeal Arcoverde, 1479"
    assert fugaz.venue.lat is None and fugaz.venue.lng is None  # RA nao da geo (0,0)
    assert fugaz.venue.category == "nightclub"
    assert fugaz.venue.source_url == "https://ra.co/clubs/9"

    baile = events[1]
    assert baile.genre == "Baile Funk"
    assert baile.venue is None  # TBA -> sem venue (nao cria lixo)


def test_parse_ra_events_vazio():
    assert parse_ra_events({}, reference=date(2099, 1, 1)) == []
    assert parse_ra_events({"data": {"eventListings": None}}, reference=date(2099, 1, 1)) == []
