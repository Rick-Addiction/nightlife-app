import httpx

from nightlife.ingestion.geocoder import GoogleGeocoder, GeocodeResult


def _fake_response(payload):
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return payload
    return _Resp()


def test_status_ok_extrai_coordenadas(monkeypatch):
    payload = {"status": "OK", "results": [
        {"geometry": {"location": {"lat": -23.55, "lng": -46.63}}}
    ]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response(payload))
    res = GoogleGeocoder("KEY").geocode("Praca da Se, Sao Paulo")
    assert res == GeocodeResult(status="OK", lat=-23.55, lng=-46.63)


def test_zero_results_sem_coordenadas(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response({"status": "ZERO_RESULTS", "results": []}))
    res = GoogleGeocoder("KEY").geocode("endereco impossivel xyz")
    assert res == GeocodeResult(status="ZERO_RESULTS")


def test_over_query_limit_vira_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response({"status": "OVER_QUERY_LIMIT", "results": []}))
    res = GoogleGeocoder("KEY").geocode("qualquer")
    assert res.status == "ERROR"


def test_excecao_de_rede_vira_error(monkeypatch):
    def _boom(*a, **k): raise httpx.ConnectError("sem rede")
    monkeypatch.setattr(httpx, "get", _boom)
    res = GoogleGeocoder("KEY").geocode("qualquer")
    assert res.status == "ERROR"


def test_ok_malformado_sem_location_vira_error(monkeypatch):
    # OK mas sem geometry/location: nao pode estourar KeyError (abortaria o run
    # inteiro e faria rollback do cache) -> degrada para ERROR (retentavel).
    payload = {"status": "OK", "results": [{"geometry": {}}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response(payload))
    res = GoogleGeocoder("KEY").geocode("resposta estranha")
    assert res.status == "ERROR"
