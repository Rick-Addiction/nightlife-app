import httpx

from nightlife.ingestion.places_client import PlacesClient, PlaceResult


def _fake_response(payload):
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return payload
    return _Resp()


class _FakeClient:
    """Client injetavel: responde um payload fixo (ou levanta); conta chamadas."""
    def __init__(self, payload=None, raises=None):
        self.payload = payload
        self.raises = raises
        self.calls = 0

    def post(self, url, headers=None, json=None):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return _fake_response(self.payload)


def _client(payload=None, raises=None):
    return PlacesClient("KEY", client=_FakeClient(payload=payload, raises=raises))


def test_parse_resultado_ok():
    payload = {"places": [
        {"id": "PID1", "displayName": {"text": "Supra Club Augusta"},
         "location": {"latitude": -23.55, "longitude": -46.66},
         "formattedAddress": "Rua Augusta, 500", "primaryType": "night_club"},
    ]}
    res = _client(payload).search_nearby(-23.55, -46.66, 1000, "night_club")
    assert res == [PlaceResult(place_id="PID1", name="Supra Club Augusta", lat=-23.55,
                               lng=-46.66, address="Rua Augusta, 500", primary_type="night_club")]


def test_descarta_sem_id_ou_sem_location():
    payload = {"places": [
        {"displayName": {"text": "Sem Id"}, "location": {"latitude": -23.5, "longitude": -46.6}},
        {"id": "PID2", "displayName": {"text": "Sem Geo"}},
    ]}
    assert _client(payload).search_nearby(-23.5, -46.6, 1000, "night_club") == []


def test_erro_de_rede_vira_lista_vazia():
    assert _client(raises=httpx.ConnectError("sem rede")).search_nearby(-23.5, -46.6, 1000, "night_club") == []


def test_resposta_de_erro_json_vira_lista_vazia():
    # a Places devolve {"error": {...}} e sem "places"
    res = _client({"error": {"code": 403, "status": "PERMISSION_DENIED"}}).search_nearby(-23.5, -46.6, 1000, "night_club")
    assert res == []


def test_resposta_estrutural_estranha_nao_estoura():
    # data nao-dict, ou um place nao-dict: nao pode estourar AttributeError (o
    # generator do PlacesSource propagaria e abortaria o run inteiro)
    assert _client(["nao", "e", "dict"]).search_nearby(-23.5, -46.6, 1000, "night_club") == []
    payload = {"places": ["string_solta", {"id": "PID9", "location": {"latitude": -23.5, "longitude": -46.6},
                                           "displayName": {"text": "Ok"}}]}
    res = _client(payload).search_nearby(-23.5, -46.6, 1000, "night_club")
    assert [r.place_id for r in res] == ["PID9"]  # o nao-dict e pulado, o valido entra


def test_reusa_um_unico_client(monkeypatch):
    # regressao Errno 24: um Client por PlacesClient, nao um por chamada
    constructed = []
    real_init = httpx.Client.__init__

    def _counting_init(self, *a, **k):
        constructed.append(1)
        real_init(self, *a, **k)

    monkeypatch.setattr(httpx.Client, "__init__", _counting_init)
    monkeypatch.setattr(httpx.Client, "post",
                        lambda self, *a, **k: _fake_response({"places": []}))
    c = PlacesClient("KEY")   # sem client injetado -> constroi o proprio
    c.search_nearby(-23.5, -46.6, 1000, "night_club")
    c.search_nearby(-23.5, -46.6, 1000, "dance_hall")
    assert len(constructed) == 1
