# tests/test_sympla_source.py
from datetime import date

from nightlife.ingestion.sympla_source import SymplaSource, parse_search_records

REF = date(2026, 6, 1)

SEARCH_JSON = {
    "data": [
        {  # festa em SP futura -> ENTRA
            "id": 111, "name": "Mamba Negra", "city": "São Paulo", "state": "SP",
            "theme_name": "Festas e Shows", "collection_name": ["FESTA E SHOW"],
            "format_name": "Festa",
            "url": "https://www.sympla.com.br/evento/mamba/111",
            "start_date_utc": "2099-06-14T02:00:00+00:00",
            "end_date_utc": "2099-06-14T09:00:00+00:00",
            "location": {"name": "Lab Club", "address": "R. Augusta, 1000",
                         "city": "São Paulo", "state": "SP",
                         "lat": -23.5613, "lon": -46.6565},
            "organizer": {"id": "77", "name": "Mamba Org"},
        },
        {  # outra cidade -> FORA
            "id": 222, "name": "Festa Carioca", "city": "Rio de Janeiro", "state": "RJ",
            "theme_name": "Festas e Shows", "collection_name": ["FESTA E SHOW"],
            "start_date_utc": "2099-06-14T02:00:00+00:00",
        },
        {  # tema errado -> FORA
            "id": 333, "name": "Curso de RCP", "city": "São Paulo", "state": "SP",
            "theme_name": "Cursos e Workshops", "collection_name": [],
            "start_date_utc": "2099-06-14T02:00:00+00:00",
        },
        {  # sem name -> FORA
            "id": 444, "city": "São Paulo", "theme_name": "Festas e Shows",
        },
        {  # passado -> FORA
            "id": 555, "name": "Festa Antiga", "city": "São Paulo", "state": "SP",
            "theme_name": "Festas e Shows", "collection_name": ["FESTA E SHOW"],
            "start_date_utc": "2020-01-01T02:00:00+00:00",
        },
    ]
}


def test_parse_search_records_filters_and_maps():
    revs = parse_search_records(SEARCH_JSON, reference=REF)
    assert [r.name for r in revs] == ["Mamba Negra"]
    r = revs[0]
    assert r.source_type == "ticketing"
    assert r.venue is not None and r.venue.name == "Lab Club"
    assert r.venue.lat == -23.5613 and r.venue.lng == -46.6565
    assert r.venue.source_type == "ticketing"
    assert r.organizer_name == "Mamba Org"
    assert r.genre == "Festa"
    assert r.ticket_url == "https://www.sympla.com.br/evento/mamba/111"
    assert r.starts_at is not None and r.starts_at.tzinfo is not None
    assert r.ends_at is not None


def test_sympla_source_other_methods_empty():
    src = SymplaSource()
    assert src.venues() == []
    assert src.event_pages() == []


def test_search_params_filter_city_server_side_and_optional_query():
    # sondagem 2026-10-28: `cityIn` nao filtra mais; `city` (string) filtra.
    base = SymplaSource().search_params(3)
    assert base["city"] == "São Paulo"
    assert base["cityIn"] == ["São Paulo"]
    assert base["page"] == 3 and base["limit"] == 100
    assert "q" not in base
    assert SymplaSource(query="halloween").search_params(1)["q"] == "halloween"


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_events_posts_city_and_query_and_stops_on_short_page(monkeypatch):
    import nightlife.ingestion.sympla_source as mod

    calls: list[dict] = []

    def fake_post(url, *, json, headers, timeout):
        calls.append(json["params"])
        return _FakeResp(SEARCH_JSON)  # 5 registros < page_size -> para na 1a pagina

    monkeypatch.setattr(mod.httpx, "post", fake_post)
    revs = SymplaSource(query="halloween", reference=REF).events()
    assert [r.name for r in revs] == ["Mamba Negra"]
    assert len(calls) == 1
    assert calls[0]["city"] == "São Paulo" and calls[0]["q"] == "halloween"
