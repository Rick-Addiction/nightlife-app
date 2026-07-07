from nightlife.domain.geo_scope import is_in_metro_sp, SP_METRO_BBOX


def test_ponto_em_sp_capital_e_dentro():
    # Praca da Se, centro de SP
    assert is_in_metro_sp(-23.5505, -46.6333) is True


def test_ponto_fora_de_sp_e_fora():
    # Itapema, Santa Catarina (o diretorio do RA arrastou)
    assert is_in_metro_sp(-27.0900, -48.6114) is False


def test_coordenada_ausente_e_fora():
    assert is_in_metro_sp(None, -46.6) is False
    assert is_in_metro_sp(-23.5, None) is False


def test_bbox_e_min_lat_max_lat_min_lng_max_lng():
    min_lat, max_lat, min_lng, max_lng = SP_METRO_BBOX
    assert min_lat < max_lat and min_lng < max_lng
