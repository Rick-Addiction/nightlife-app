# tests/test_mock_source.py
from pathlib import Path

from nightlife.ingestion.base import RawVenue, RawEventPage
from nightlife.ingestion.mock_source import MockSource

FIXTURES = Path(__file__).parent.parent / "src" / "nightlife" / "fixtures"


def test_loads_fixtures():
    src = MockSource.from_fixtures(FIXTURES / "venues.json", FIXTURES / "event_pages.json")
    venues = list(src.venues())
    pages = list(src.event_pages())
    assert len(venues) >= 3 and all(isinstance(v, RawVenue) for v in venues)
    assert len(pages) >= 3 and all(isinstance(p, RawEventPage) for p in pages)
    # ha pelo menos uma pagina de cada tipo coberto
    kinds = {p.kind for p in pages}
    assert {"jsonld", "html", "freetext"} <= kinds


def test_in_memory_construction():
    src = MockSource([RawVenue(name="X", source_type="osm")], [])
    assert list(src.venues())[0].name == "X"
    assert list(src.event_pages()) == []
