from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue, GeocodeCache
from nightlife.ingestion.geocoder import GeocodeResult
from nightlife.geocode_venues import geocode_all

REF = date(2026, 6, 1)


class FakeGeocoder:
    """Geocoder de teste: responde por endereco e conta chamadas."""
    def __init__(self, table):
        self.table = table          # dict endereco-substring -> GeocodeResult
        self.calls = 0

    def geocode(self, address):
        self.calls += 1
        for key, res in self.table.items():
            if key in address:
                return res
        return GeocodeResult(status="ZERO_RESULTS")


def _venue(session, name, address, **kw):
    v = Venue(name=name, address=address, **kw)
    session.add(v)
    session.flush()
    return v


def test_backfill_preenche_geo_dos_sem_geo(session):
    v = _venue(session, "D-Edge", "Alameda Olga, 170 Sao Paulo")
    g = FakeGeocoder({"Olga": GeocodeResult(status="OK", lat=-23.53, lng=-46.66)})
    out = geocode_all(session, g, reference=REF)
    session.flush()
    assert session.get(Venue, v.id).lat == -23.53
    assert out["geocoded"] == 1


def test_zero_results_fica_sem_geo(session):
    v = _venue(session, "Lugar Ruim", "endereco impossivel")
    g = FakeGeocoder({})   # tudo cai em ZERO_RESULTS
    geocode_all(session, g, reference=REF)
    session.flush()
    assert session.get(Venue, v.id).lat is None


def test_venue_sem_address_e_ignorado(session):
    v = _venue(session, "Sem Endereco", None)
    g = FakeGeocoder({"x": GeocodeResult(status="OK", lat=-23.5, lng=-46.6)})
    geocode_all(session, g, reference=REF)
    assert g.calls == 0   # nao chamou o geocoder


def test_rerun_usa_cache_e_nao_rechama(session):
    _venue(session, "D-Edge", "Alameda Olga, 170 Sao Paulo")
    g = FakeGeocoder({"Olga": GeocodeResult(status="OK", lat=-23.53, lng=-46.66)})
    geocode_all(session, g, reference=REF)
    session.flush()
    # segundo venue com o MESMO endereco, novo run: cache serve, geocoder nao e chamado de novo
    _venue(session, "D-Edge (dup)", "Alameda Olga, 170 Sao Paulo")
    calls_antes = g.calls
    geocode_all(session, g, reference=REF)
    assert g.calls == calls_antes   # 0 novas chamadas (cache hit)


def test_relatorio_separa_error_de_zero_results(session):
    # ERROR (quota/rede) nao pode ser contado como ZERO_RESULTS: esconderia
    # "API caiu" no run real. O endereco nao geocodado fica sem geo.
    v = _venue(session, "Quota Estourada", "Rua Z Sao Paulo")
    g = FakeGeocoder({"Sao Paulo": GeocodeResult(status="ERROR")})
    out = geocode_all(session, g, reference=REF)
    session.flush()
    assert out["errors"] == 1 and out["zero_results"] == 0
    assert session.get(Venue, v.id).lat is None


def test_relatorio_conta_in_out_sp(session):
    _venue(session, "Em SP", "Rua A Sao Paulo")
    _venue(session, "Fora SP", "Rua B Itapema")
    g = FakeGeocoder({
        "Sao Paulo": GeocodeResult(status="OK", lat=-23.55, lng=-46.63),
        "Itapema": GeocodeResult(status="OK", lat=-27.09, lng=-48.61),
    })
    out = geocode_all(session, g, reference=REF)
    assert out["in_sp"] == 1 and out["out_sp"] == 1
