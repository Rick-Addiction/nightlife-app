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


from nightlife.ingestion import ra_source


def test_ra_source_paginates_e_para(monkeypatch):
    ev = {"event": {"id": "1", "title": "E", "date": "2099-07-08T00:00:00.000",
                    "startTime": "2099-07-08T22:00:00.000", "contentUrl": "/events/1",
                    "artists": [], "genres": [], "venue": {"name": "V", "contentUrl": "/clubs/1"}}}
    pages = {
        1: {"data": {"eventListings": {"data": [ev, ev]}}},   # cheia (== page_size 2)
        2: {"data": {"eventListings": {"data": [ev]}}},        # < page_size -> para
    }
    seen = []

    class _Resp:
        def __init__(self, d): self._d = d
        def raise_for_status(self): pass
        def json(self): return self._d

    def fake_post(url, **kw):
        page = kw["json"]["variables"]["page"]
        seen.append(page)
        return _Resp(pages.get(page, {"data": {"eventListings": {"data": []}}}))

    monkeypatch.setattr(ra_source.httpx, "post", fake_post)
    src = ra_source.RASource(page_size=2, reference=date(2099, 1, 1))
    events = src.events()
    assert seen == [1, 2]                 # parou na pagina 2 (veio < page_size)
    assert len(events) == 3               # 2 + 1
    assert src.event_pages() == []


from nightlife.ingestion.ra_source import parse_ra_venues

RA_VENUES = {"data": {"venues": [
    {"id": "4973", "name": "D-EDGE", "address": "Alameda Olga, 170",
     "contentUrl": "/clubs/4973", "eventCountThisYear": 12, "isClosed": False},
    {"id": "1", "name": "Fechado", "address": "X",
     "contentUrl": "/clubs/1", "eventCountThisYear": 0, "isClosed": True},   # fechado -> fora
    {"id": "2", "name": "TBA - Rua Y", "address": None,
     "contentUrl": None, "eventCountThisYear": 0, "isClosed": False},        # TBA -> fora
    {"id": "3", "name": "", "address": None,
     "contentUrl": "/clubs/3", "eventCountThisYear": 0, "isClosed": False},  # sem nome -> fora
]}}


def test_parse_ra_venues():
    vs = parse_ra_venues(RA_VENUES)
    assert [v.name for v in vs] == ["D-EDGE"]   # fechado/TBA/vazio descartados
    d = vs[0]
    assert d.source_type == "ra"
    assert d.category == "nightclub"
    assert d.lat is None and d.lng is None       # RA nao da geo
    assert d.address == "Alameda Olga, 170"
    assert d.source_url == "https://ra.co/clubs/4973"


def test_parse_ra_venues_vazio():
    assert parse_ra_venues({}) == []
    assert parse_ra_venues({"data": {"venues": None}}) == []


def test_ra_source_venues_busca_diretorio(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"data": {"venues": [
                {"id": "4973", "name": "D-EDGE", "address": "Alameda Olga, 170",
                 "contentUrl": "/clubs/4973", "isClosed": False}]}}

    def fake_post(url, **kw):
        captured.update(kw["json"]["variables"])
        return _Resp()

    monkeypatch.setattr(ra_source.httpx, "post", fake_post)
    src = ra_source.RASource()
    vs = src.venues()
    assert captured["o"] == "ALPHABETICAL"
    assert captured["l"] == 20              # quirk do RA: limit<=20 traz os 684
    assert captured["a"] == 400             # SP
    assert [v.name for v in vs] == ["D-EDGE"]
