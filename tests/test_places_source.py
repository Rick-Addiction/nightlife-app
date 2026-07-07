from nightlife.ingestion.base import RawVenue
from nightlife.ingestion.places_client import PlaceResult
from nightlife.ingestion.places_source import PlacesSource, _category_for, SEED_POINTS, SEARCH_TYPES


class _FakePlacesClient:
    """Devolve resultados por tipo e registra as chamadas."""
    def __init__(self, by_type=None):
        self.by_type = by_type or {}
        self.calls = []

    def search_nearby(self, lat, lng, radius, included_type):
        self.calls.append((lat, lng, radius, included_type))
        return list(self.by_type.get(included_type, []))


def test_category_for_mapeia_por_primary_type():
    assert _category_for("night_club") == "nightclub"
    assert _category_for("dance_hall") == "nightclub"
    assert _category_for("live_music_venue") == "nightclub"
    assert _category_for("concert_hall") == "nightclub"
    assert _category_for("bar") == "bar"          # vazou via tipo secundario
    assert _category_for(None) == "bar"


def test_venues_itera_semente_x_tipo_e_mapeia():
    pr = PlaceResult(place_id="PID1", name="Supra Club Augusta", lat=-23.55, lng=-46.66,
                     address="Rua Augusta, 500", primary_type="night_club")
    client = _FakePlacesClient(by_type={"night_club": [pr]})
    src = PlacesSource(client, seeds=[("Augusta", -23.5545, -46.6620)],
                       types=("night_club", "dance_hall"), radius=1000)
    vs = list(src.venues())
    # 1 semente x 2 tipos = 2 chamadas
    assert len(client.calls) == 2
    assert client.calls[0] == (-23.5545, -46.6620, 1000, "night_club")
    # so night_club retornou algo
    assert vs == [RawVenue(name="Supra Club Augusta", source_type="google_places",
                           lat=-23.55, lng=-46.66, address="Rua Augusta, 500",
                           category="nightclub", source_url="PID1")]


def test_venues_loga_saturacao_em_20():
    lots = [PlaceResult(place_id=f"P{i}", name=f"Club {i}", lat=-23.5, lng=-46.6,
                        address=None, primary_type="night_club") for i in range(20)]
    client = _FakePlacesClient(by_type={"night_club": lots})
    logs = []
    src = PlacesSource(client, seeds=[("Augusta", -23.5, -46.6)],
                       types=("night_club",), radius=1000, log=logs.append)
    list(src.venues())
    assert any("satur" in m.lower() for m in logs)


def test_event_pages_e_events_vazios():
    src = PlacesSource(_FakePlacesClient())
    assert list(src.event_pages()) == []
    assert list(src.events()) == []


def test_defaults_de_seeds_e_types_existem():
    assert len(SEED_POINTS) >= 10
    assert "night_club" in SEARCH_TYPES and "event_venue" not in SEARCH_TYPES
