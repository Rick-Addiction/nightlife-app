from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue
from nightlife.ingestion.places_client import PlaceResult
from nightlife.discover_places import discover

REF = date(2026, 6, 1)


class _FakePlacesClient:
    def __init__(self, by_type=None):
        self.by_type = by_type or {}

    def search_nearby(self, lat, lng, radius, included_type):
        return list(self.by_type.get(included_type, []))


def test_discover_cria_venues(session):
    pr = PlaceResult(place_id="PID1", name="Supra Club Augusta", lat=-23.55, lng=-46.66,
                     address="Rua Augusta, 500", primary_type="night_club")
    from nightlife.ingestion.places_source import PlacesSource
    src = PlacesSource(_FakePlacesClient({"night_club": [pr]}),
                       seeds=[("Augusta", -23.5545, -46.6620)], types=("night_club",))
    run = discover(session, src, reference=REF)
    session.flush()
    assert run.status == "finished"
    assert session.scalar(select(func.count()).select_from(Venue)) == 1


def test_discover_reingest_idempotente(session):
    pr = PlaceResult(place_id="PID1", name="Supra Club Augusta", lat=-23.55, lng=-46.66,
                     address="Rua Augusta, 500", primary_type="night_club")
    from nightlife.ingestion.places_source import PlacesSource
    mk = lambda: PlacesSource(_FakePlacesClient({"night_club": [pr]}),
                              seeds=[("Augusta", -23.5545, -46.6620)], types=("night_club",))
    discover(session, mk(), reference=REF)
    session.flush()
    discover(session, mk(), reference=REF)
    session.flush()
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
