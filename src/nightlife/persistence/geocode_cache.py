"""Cache de geocoding (endereco normalizado -> coordenada), idempotente entre
runs. Garante que o mesmo endereco nunca e cobrado 2x na Google. ZERO_RESULTS e
cacheado como negativo (endereco ruim nao melhora sozinho); ERROR nao e gravado
(transitorio — tenta de novo no proximo run)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..ingestion.geocoder import GeocodeResult
from ..models import GeocodeCache


def normalize_address(address: str) -> str:
    return " ".join(address.split()).lower()


def cache_lookup(session: Session, address: str) -> GeocodeResult | None:
    row = session.get(GeocodeCache, normalize_address(address))
    if row is None:
        return None
    return GeocodeResult(status=row.status, lat=row.lat, lng=row.lng)


def cache_store(session: Session, address: str, result: GeocodeResult) -> None:
    if result.status == "ERROR":
        return  # transitorio: nao cacheia
    key = normalize_address(address)
    row = session.get(GeocodeCache, key)
    if row is None:
        row = GeocodeCache(address_norm=key)
        session.add(row)
    row.status = result.status
    row.lat = result.lat
    row.lng = result.lng
    session.flush()
