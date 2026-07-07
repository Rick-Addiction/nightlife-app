"""Geocoding: endereco em texto -> coordenadas, via Google Geocoding API.

O protocolo Geocoder permite injetar um fake nos testes (zero rede). Status
mapeados: OK (coords), ZERO_RESULTS (endereco nao resolvido, cacheavel como
negativo), ERROR (transitorio: quota/rede/chave — NAO cacheia, tenta de novo)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

_ENDPOINT = "https://maps.googleapis.com/maps/api/geocode/json"
_TIMEOUT = 15.0


@dataclass(frozen=True)
class GeocodeResult:
    status: str                 # "OK" | "ZERO_RESULTS" | "ERROR"
    lat: float | None = None
    lng: float | None = None


class Geocoder(Protocol):
    def geocode(self, address: str) -> GeocodeResult: ...


class GoogleGeocoder:
    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def geocode(self, address: str) -> GeocodeResult:
        params = {
            "address": address,
            "key": self._key,
            "region": "br",
            "components": "country:BR",
        }
        try:
            resp = httpx.get(_ENDPOINT, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return GeocodeResult(status="ERROR")

        status = data.get("status")
        if status == "OK" and data.get("results"):
            # extracao defensiva: um OK malformado (sem geometry/location) vira
            # ERROR retentavel, nunca estoura para fora e aborta o backfill.
            try:
                loc = data["results"][0]["geometry"]["location"]
                return GeocodeResult(status="OK", lat=loc["lat"], lng=loc["lng"])
            except (KeyError, IndexError, TypeError):
                return GeocodeResult(status="ERROR")
        if status == "ZERO_RESULTS":
            return GeocodeResult(status="ZERO_RESULTS")
        return GeocodeResult(status="ERROR")
