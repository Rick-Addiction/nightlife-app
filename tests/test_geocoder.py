import httpx

from nightlife.ingestion.geocoder import GoogleGeocoder, GeocodeResult


def _fake_response(payload):
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return payload
    return _Resp()


class _FakeClient:
    """Client injetavel: responde sempre o mesmo payload (ou levanta)."""
    def __init__(self, payload=None, raises=None):
        self.payload = payload
        self.raises = raises
        self.calls = 0

    def get(self, url, params=None):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return _fake_response(self.payload)


def _geocoder(payload=None, raises=None):
    return GoogleGeocoder("KEY", client=_FakeClient(payload=payload, raises=raises))


def test_status_ok_extrai_coordenadas():
    g = _geocoder({"status": "OK", "results": [
        {"geometry": {"location": {"lat": -23.55, "lng": -46.63}}}
    ]})
    assert g.geocode("Praca da Se, Sao Paulo") == GeocodeResult(status="OK", lat=-23.55, lng=-46.63)


def test_zero_results_sem_coordenadas():
    g = _geocoder({"status": "ZERO_RESULTS", "results": []})
    assert g.geocode("endereco impossivel xyz") == GeocodeResult(status="ZERO_RESULTS")


def test_over_query_limit_vira_error():
    g = _geocoder({"status": "OVER_QUERY_LIMIT", "results": []})
    assert g.geocode("qualquer").status == "ERROR"


def test_excecao_de_rede_vira_error():
    g = _geocoder(raises=httpx.ConnectError("sem rede"))
    assert g.geocode("qualquer").status == "ERROR"


def test_ok_malformado_sem_location_vira_error():
    # OK mas sem geometry/location: nao pode estourar KeyError (abortaria o run
    # inteiro e faria rollback do cache) -> degrada para ERROR (retentavel).
    g = _geocoder({"status": "OK", "results": [{"geometry": {}}]})
    assert g.geocode("resposta estranha").status == "ERROR"


def test_reusa_um_unico_client_entre_chamadas(monkeypatch):
    # regressao: httpx.get() construiria um Client novo por chamada -> em ~600
    # chamadas estoura "Too many open files" (Errno 24). O geocoder deve construir
    # UM Client e reusa-lo em todas as chamadas.
    constructed = []
    real_init = httpx.Client.__init__

    def _counting_init(self, *a, **k):
        constructed.append(1)
        real_init(self, *a, **k)

    monkeypatch.setattr(httpx.Client, "__init__", _counting_init)
    monkeypatch.setattr(httpx.Client, "get",
                        lambda self, *a, **k: _fake_response({"status": "ZERO_RESULTS", "results": []}))
    g = GoogleGeocoder("KEY")   # sem client injetado -> constroi o proprio
    g.geocode("a"); g.geocode("b"); g.geocode("c")
    assert len(constructed) == 1   # um Client pro geocoder, nao um por chamada
