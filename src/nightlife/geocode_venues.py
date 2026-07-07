"""Geocoda venues sem geo (endereco -> lat/lng) via Google e re-dedupa os que
ganharam geo. Backfill uma vez + passo diario, ambos com cache.

Uso: .venv/Scripts/python -m nightlife.geocode_venues
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain.geo_scope import is_in_metro_sp
from .ingestion.geocoder import Geocoder
from .models import Venue
from .persistence.geocode_cache import cache_lookup, cache_store
from .persistence.venue_merge import rededup_geocoded

_SP_TZ = ZoneInfo("America/Sao_Paulo")


def geocode_all(session: Session, geocoder: Geocoder, *, reference: date) -> dict:
    pend = session.scalars(
        select(Venue).where(Venue.lat.is_(None), Venue.address.is_not(None))
    ).all()

    geocoded_ids: list[int] = []
    in_sp = out_sp = zero = errors = 0
    for v in pend:
        res = cache_lookup(session, v.address)
        if res is None:
            res = geocoder.geocode(v.address)
            cache_store(session, v.address, res)
        if res.status == "OK":
            v.lat, v.lng = res.lat, res.lng
            geocoded_ids.append(v.id)
            if is_in_metro_sp(res.lat, res.lng):
                in_sp += 1
            else:
                out_sp += 1
        elif res.status == "ZERO_RESULTS":
            zero += 1
        else:  # ERROR (quota/rede/chave): nao cacheado, tenta de novo no proximo
            errors += 1
    session.flush()

    dd = rededup_geocoded(session, geocoded_ids, reference=reference)
    return {"geocoded": len(geocoded_ids), "in_sp": in_sp, "out_sp": out_sp,
            "zero_results": zero, "errors": errors, **dd}


def main() -> None:
    from .config import GOOGLE_MAPS_API_KEY

    if not GOOGLE_MAPS_API_KEY:
        print("ERRO: defina GOOGLE_MAPS_API_KEY (Geocoding API + billing no Google Cloud)")
        sys.exit(1)

    import truststore
    truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

    from .db import SessionLocal
    from .ingestion.geocoder import GoogleGeocoder

    today = datetime.now(_SP_TZ).date()
    with SessionLocal() as session:
        out = geocode_all(session, GoogleGeocoder(GOOGLE_MAPS_API_KEY), reference=today)
        session.commit()
        print(f"geocoded={out['geocoded']} (in_sp={out['in_sp']} out_sp={out['out_sp']} "
              f"zero_results={out['zero_results']} errors={out['errors']}) | "
              f"merged={out['merged']} review={out['review']} distinct={out['distinct']}")


if __name__ == "__main__":
    main()
