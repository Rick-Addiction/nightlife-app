"""Escopo geografico: 'este ponto esta na Regiao Metropolitana de SP?' (puro).

O diretorio do RA trouxe venues de outras cidades (Itapema/SC, Ubatuba). Depois
de geocodar, esta funcao permite filtrar por localizacao de verdade — coisa que
o texto do endereco nao dava. Usada no relatorio do runner de geocoding."""
from __future__ import annotations

# bbox aproximado da RMSP: (min_lat, max_lat, min_lng, max_lng).
# Cobre a Grande SP com folga (Guarulhos, ABC, Osasco, Barueri).
SP_METRO_BBOX: tuple[float, float, float, float] = (-24.10, -23.30, -47.10, -46.30)


def is_in_metro_sp(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    min_lat, max_lat, min_lng, max_lng = SP_METRO_BBOX
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng
