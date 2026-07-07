# tests/test_geocode_cache_model.py
from nightlife.models import GeocodeCache


def test_geocode_cache_persiste_e_le(session):
    session.add(GeocodeCache(address_norm="rua x, 1 sao paulo", status="OK",
                             lat=-23.5, lng=-46.6))
    session.flush()
    row = session.get(GeocodeCache, "rua x, 1 sao paulo")
    assert row is not None and row.status == "OK" and row.lat == -23.5
