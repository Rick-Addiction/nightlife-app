from nightlife.ingestion.geocoder import GeocodeResult
from nightlife.persistence.geocode_cache import normalize_address, cache_lookup, cache_store
from nightlife.models import GeocodeCache
from sqlalchemy import select, func


def test_normalize_colapsa_espacos_e_caixa():
    assert normalize_address("  Rua  X,  1   São Paulo ") == "rua x, 1 são paulo"
    assert normalize_address("RUA X, 1 SÃO PAULO") == normalize_address("rua x, 1 são paulo")


def test_lookup_miss_retorna_none(session):
    assert cache_lookup(session, "rua inexistente") is None


def test_store_ok_e_recuperavel(session):
    cache_store(session, "Rua X, 1", GeocodeResult(status="OK", lat=-23.5, lng=-46.6))
    hit = cache_lookup(session, "rua x, 1")   # case-insensitive via normalize
    assert hit == GeocodeResult(status="OK", lat=-23.5, lng=-46.6)


def test_store_zero_results_e_cacheado_negativo(session):
    cache_store(session, "endereco ruim", GeocodeResult(status="ZERO_RESULTS"))
    hit = cache_lookup(session, "endereco ruim")
    assert hit == GeocodeResult(status="ZERO_RESULTS", lat=None, lng=None)


def test_store_error_nao_grava(session):
    cache_store(session, "transitorio", GeocodeResult(status="ERROR"))
    assert cache_lookup(session, "transitorio") is None
    n = session.scalar(select(func.count()).select_from(GeocodeCache))
    assert n == 0


def test_store_e_idempotente_no_mesmo_endereco(session):
    cache_store(session, "Rua Y, 2", GeocodeResult(status="OK", lat=-23.1, lng=-46.1))
    cache_store(session, "rua y, 2", GeocodeResult(status="OK", lat=-23.2, lng=-46.2))
    n = session.scalar(select(func.count()).select_from(GeocodeCache))
    assert n == 1  # mesma chave normalizada -> update, nao segunda linha
