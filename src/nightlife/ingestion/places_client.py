"""Cliente da Google Places API (New) — Nearby Search (places:searchNearby).

Descoberta geografica: dado ponto+raio+tipo, devolve os lugares COM geo e
place_id. Um httpx.Client reutilizado (senao Errno 24 em muitas chamadas). Field
mask no tier Pro (id/nome/geo/endereco/tipo) — sem rating/reviews, custo menor."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

_ENDPOINT = "https://places.googleapis.com/v1/places:searchNearby"
_FIELD_MASK = ("places.id,places.displayName,places.location,"
               "places.formattedAddress,places.primaryType,places.businessStatus")
_TIMEOUT = 20.0


@dataclass(frozen=True)
class PlaceResult:
    place_id: str
    name: str
    lat: float
    lng: float
    address: str | None
    primary_type: str | None
    business_status: str | None = None


class PlacesClient:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.Client(timeout=_TIMEOUT)

    def search_nearby(self, lat: float, lng: float, radius: float,
                      included_type: str) -> list[PlaceResult]:
        body = {
            "includedTypes": [included_type],
            "maxResultCount": 20,
            "rankPreference": "DISTANCE",
            "locationRestriction": {"circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius)}},
            # sem isso a API serve o indice EN com alias VELHO (caso Selva/Inferno)
            "languageCode": "pt-BR",
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }
        try:
            resp = self._client.post(_ENDPOINT, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []

        if not isinstance(data, dict):
            return []  # resposta estrutural estranha nao aborta o run inteiro
        out: list[PlaceResult] = []
        for p in data.get("places", []):
            if not isinstance(p, dict):
                continue
            loc = p.get("location") or {}
            pid, lat_, lng_ = p.get("id"), loc.get("latitude"), loc.get("longitude")
            if not pid or lat_ is None or lng_ is None:
                continue  # sem identidade ou sem geo: descarta defensivamente
            out.append(PlaceResult(
                place_id=pid,
                name=(p.get("displayName") or {}).get("text", ""),
                lat=lat_, lng=lng_,
                address=p.get("formattedAddress"),
                primary_type=p.get("primaryType"),
                business_status=p.get("businessStatus"),
            ))
        return out
