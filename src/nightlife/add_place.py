"""Adiciona um venue pontual via Google Places Text Search (spec E-1 Task 9).

Diferente do discover_places (geografico, tipo x raio), aqui o usuario digita
o NOME e o Google acha o lugar certo mesmo com grafia/apelido — util quando o
Nearby nao acha (fora do raio das sementes, saturado, ou tipo secundario que
o Nearby nao cobre).

Uso: .venv/Scripts/python -m nightlife.add_place "supra club augusta"
     .venv/Scripts/python -m nightlife.add_place "supra club augusta" --pick 1
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .ingestion.places_source import _NIGHTCLUB_TYPES
from .models import Venue
from .persistence.inputs import SourceInfo, VenueInput
from .persistence.venues_repo import upsert_venue

_SP_TZ = ZoneInfo("America/Sao_Paulo")
# vies de centro: media aproximada da regiao central de SP (a API so usa o
# vies pra RANQUEAR, nao restringe — texto ambiguo em outra cidade ainda acha)
_SP_CENTER_LAT = -23.5613
_SP_CENTER_LNG = -46.6560


@dataclass(frozen=True)
class Match:
    place_id: str
    name: str
    address: str | None
    lat: float
    lng: float
    types: list[str]
    business_status: str | None = None


def parse_matches(resp: dict) -> list[Match]:
    """Extrai os candidatos do dict CRU da Text Search API. Descarta
    resultados sem place_id ou geo (mesma defesa do places_client)."""
    out: list[Match] = []
    for p in resp.get("places", []):
        if not isinstance(p, dict):
            continue
        loc = p.get("location") or {}
        pid, lat, lng = p.get("id"), loc.get("latitude"), loc.get("longitude")
        if not pid or lat is None or lng is None:
            continue
        out.append(Match(
            place_id=pid,
            name=(p.get("displayName") or {}).get("text", ""),
            address=p.get("formattedAddress"),
            lat=lat, lng=lng,
            types=list(p.get("types") or []),
            business_status=p.get("businessStatus"),
        ))
    return out


def _category_for(types: list[str]) -> str:
    return "nightclub" if any(t in _NIGHTCLUB_TYPES for t in types) else "bar"


def ingest_pick(session: Session, match: Match, *, reference: date) -> Venue:
    """Espelha EXATAMENTE o formato do places_source (mesmo source_type e
    source_url=place_id) — senao o dedupe-por-place_id do upsert_venue nao
    reconhece o venue no proximo discover_places/enrich."""
    return upsert_venue(
        session,
        VenueInput(name=match.name, lat=match.lat, lng=match.lng,
                   address=match.address, category=_category_for(match.types)),
        SourceInfo(source_type="google_places", source_url=match.place_id),
        reference=reference,
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="nome/apelido do lugar, ex: 'supra club augusta'")
    ap.add_argument("--pick", type=int, default=None,
                    help="indice (1-based) do match a ingerir quando houver varios")
    args = ap.parse_args(argv)

    from .config import GOOGLE_MAPS_API_KEY

    if not GOOGLE_MAPS_API_KEY:
        print("ERRO: defina GOOGLE_MAPS_API_KEY (e habilite a Places API New no Google Cloud)")
        sys.exit(1)

    import truststore
    truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

    from .db import SessionLocal
    from .ingestion.places_client import PlacesClient

    client = PlacesClient(GOOGLE_MAPS_API_KEY)
    resp = client.search_text(args.query, lat=_SP_CENTER_LAT, lng=_SP_CENTER_LNG)
    matches = parse_matches(resp)
    if not matches:
        print(f"nenhum resultado pra {args.query!r}")
        sys.exit(1)

    for i, m in enumerate(matches, start=1):
        print(f"{i}. {m.name} — {m.address or '(sem endereco)'} "
              f"[types={m.types}] status={m.business_status}")

    if len(matches) == 1:
        pick = matches[0]
    elif args.pick is not None:
        if not (1 <= args.pick <= len(matches)):
            print(f"--pick invalido: escolha entre 1 e {len(matches)}")
            sys.exit(1)
        pick = matches[args.pick - 1]
    else:
        print(f"\n{len(matches)} resultados — rode de novo com --pick N pra escolher")
        return

    today = datetime.now(_SP_TZ).date()
    with SessionLocal() as session:
        venue = ingest_pick(session, pick, reference=today)
        session.commit()
        print(f"venue #{venue.id} {venue.name!r} (category={venue.category}) ingerido")


if __name__ == "__main__":
    main()
