# tests/test_daily_steps.py
from nightlife.daily import STEPS


def test_geocode_venues_roda_depois_do_ra():
    names = [name for name, _ in STEPS]
    assert "geocode_venues" in names
    assert names.index("geocode_venues") > names.index("ingest_ra")


def test_geocode_step_invoca_o_modulo_certo():
    argv = dict(STEPS)["geocode_venues"]
    assert argv[-2:] == ["-m", "nightlife.geocode_venues"]
