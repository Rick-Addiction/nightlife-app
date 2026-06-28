# tests/test_jsonld.py
from nightlife.extraction.jsonld import parse_jsonld_events

PAGE_SINGLE = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Event","name":"Mamba Negra",
 "startDate":"2026-06-13T23:00:00-03:00",
 "location":{"@type":"Place","name":"Lab Club"},
 "offers":{"@type":"Offer","url":"https://sympla.com.br/e/mamba"}}
</script></head><body></body></html>
"""

PAGE_GRAPH = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebSite","name":"Agenda"},
  {"@type":["Event","MusicEvent"],"name":"Carlos Capslock","startDate":"2026-07-20T22:00:00-03:00"}
]}
</script></head><body></body></html>
"""

PAGE_NONE = "<html><body><p>sem dados estruturados</p></body></html>"
PAGE_BROKEN = '<script type="application/ld+json">{not valid json,,}</script>'


def test_parses_single_event():
    evs = parse_jsonld_events(PAGE_SINGLE, source_url="http://x")
    assert len(evs) == 1
    e = evs[0]
    assert e.name == "Mamba Negra"
    assert e.venue_name == "Lab Club"
    assert e.ticket_url == "https://sympla.com.br/e/mamba"
    assert e.starts_at is not None and e.starts_at.hour == 23
    assert e.source_url == "http://x"


def test_parses_event_inside_graph_and_type_list():
    evs = parse_jsonld_events(PAGE_GRAPH)
    assert [e.name for e in evs] == ["Carlos Capslock"]


def test_no_jsonld_returns_empty():
    assert parse_jsonld_events(PAGE_NONE) == []


def test_broken_jsonld_is_ignored():
    assert parse_jsonld_events(PAGE_BROKEN) == []
