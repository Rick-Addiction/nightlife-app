"""Enriquecimento de venues via Place Details + reconciliacao (Ciclo A).

Details por place_id: nome canonico pt-BR (renomeia com trilha), businessStatus
(mata fechados), websiteUri (site oficial -> elo do Ciclo B). Cache de 30 dias
via enriched_at. Sob demanda: python -m nightlife.enrich_places
"""
from __future__ import annotations

import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import distinct, or_, select
from sqlalchemy.orm import Session

from .domain.matching import _haversine_km, name_similarity
from .models import DedupeCandidate, Event, Venue, VenueSource, VerificationLog
from .persistence.venue_merge import _pick_survivor, merge_venues

_STATUS_MAP = {
    "OPERATIONAL": "operational",
    "CLOSED_TEMPORARILY": "closed",
    "CLOSED_PERMANENTLY": "permanently_closed",
}


def _place_ids_by_venue(session: Session) -> dict[int, str]:
    """place_id (source_url) mais recente por venue com evidencia google_places."""
    rows = session.execute(
        select(VenueSource.venue_id, VenueSource.source_url)
        .where(VenueSource.source_type == "google_places",
               VenueSource.source_url.is_not(None))
        .order_by(VenueSource.venue_id, VenueSource.last_seen_at.desc())
    ).all()
    out: dict[int, str] = {}
    for vid, url in rows:
        out.setdefault(vid, url)    # primeiro = last_seen mais recente
    return out


def enrich_all(session: Session, client, *, now: datetime, max_age_days: int = 30) -> dict:
    out = {"enriched": 0, "renamed": 0, "websites_set": 0, "closed_perm": 0,
           "closed_temp": 0, "skipped_cached": 0, "errors": 0}
    cutoff = now - timedelta(days=max_age_days)
    for vid, pid in _place_ids_by_venue(session).items():
        venue = session.get(Venue, vid)
        if venue is None:
            continue
        if venue.enriched_at is not None and venue.enriched_at >= cutoff:
            out["skipped_cached"] += 1
            continue
        det = client.place_details(pid)
        if det is None:
            out["errors"] += 1      # retentavel: NAO grava enriched_at
            continue
        if det.name and det.name != venue.name:
            session.add(VerificationLog(
                entity_type="venue", entity_id=venue.id,
                note=f"rename: {venue.name!r} -> {det.name!r} (places)"))
            venue.name = det.name
            out["renamed"] += 1
        if det.website and det.website != venue.website:
            venue.website = det.website
            out["websites_set"] += 1
        if det.business_status is not None:
            # Details sem businessStatus nao ANULA um status ja conhecido
            venue.business_status = det.business_status
            mapped = _STATUS_MAP.get(det.business_status)
            if mapped:
                venue.status = mapped
        if det.business_status == "CLOSED_PERMANENTLY":
            out["closed_perm"] += 1
        elif det.business_status == "CLOSED_TEMPORARILY":
            out["closed_temp"] += 1
        venue.enriched_at = now
        out["enriched"] += 1
    session.flush()
    return out


def _sources_by_venue(session: Session) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for vid, stype in session.execute(select(VenueSource.venue_id, VenueSource.source_type)):
        out.setdefault(vid, set()).add(stype)
    return out


_STREET_TYPES = {"r", "rua", "av", "avenida", "al", "alameda", "tv", "travessa",
                 "pc", "pca", "praca", "lgo", "largo", "estr", "estrada", "rod", "rodovia"}


def _street(address: str | None) -> str:
    """Nome da rua de um endereco livre (tokens antes do primeiro numero, sem o
    tipo de logradouro), normalizado. '' quando nao extraivel."""
    if not address:
        return ""
    s = unicodedata.normalize("NFKD", address).encode("ascii", "ignore").decode().lower()
    seg = re.split(r"[;,]", s)[0]
    toks: list[str] = []
    for tok in seg.split():
        tok = tok.strip(".")
        if any(ch.isdigit() for ch in tok):
            break
        if tok:
            toks.append(tok)
    if toks and toks[0] in _STREET_TYPES:
        toks = toks[1:]
    return " ".join(toks)


def _streets_differ(a: str | None, b: str | None) -> bool:
    """True so quando AMBOS tem rua extraivel e elas divergem (enderecos em
    ruas diferentes = lugares diferentes, por mais que os nomes se paream)."""
    sa, sb = _street(a), _street(b)
    return bool(sa) and bool(sb) and sa != sb and sa not in sb and sb not in sa


def _queue_review(session: Session, a: Venue, b: Venue, sim: float) -> None:
    """Enfileira o par pra revisao humana (sem duplicar par existente)."""
    exists = session.scalars(select(DedupeCandidate).where(
        DedupeCandidate.kind == "venue",
        or_((DedupeCandidate.a_id == a.id) & (DedupeCandidate.b_id == b.id),
            (DedupeCandidate.a_id == b.id) & (DedupeCandidate.b_id == a.id)),
    )).first()
    if exists is None:
        session.add(DedupeCandidate(kind="venue", a_id=a.id, b_id=b.id,
                                    similarity_score=sim, decision="review"))


def reconcile_venues(session: Session, *, reference: date) -> dict:
    """Duas regras, nesta ordem. 1) Consolidacao: par <=30m com name_similarity
    CRUA >= 0.70 e >=1 lado verificado -> merge; a faixa 0.60-0.70 e AMBIGUA
    (Kat Klub 0.615 = mesmo clube; Funilaria/Redoma 0.621 = clubes diferentes,
    medido em producao) -> fila de review. Vetos que tambem mandam pra review:
    dois place_ids distintos (o Google diz que sao dois negocios) e ruas
    diferentes nos enderecos. 2) Supersessao: fantasma (1 fonte ra/osm, 0
    eventos) com exatamente 1 verificado <=30m e SEM conflito de rua -> funde
    nele (Inferno->Selva, Beco->Kat Klub); ambiguidade -> review. Merge e
    delete fisico: na duvida, review. Tudo via merge_venues (auditavel)."""
    out = {"consolidated": 0, "superseded": 0, "review_queued": 0, "untouched": 0}

    def _snapshot():
        srcs = _sources_by_venue(session)
        with_ev = set(session.scalars(
            select(distinct(Event.venue_id)).where(Event.venue_id.is_not(None))))
        venues = session.scalars(select(Venue).where(
            Venue.lat.is_not(None), Venue.lng.is_not(None))).all()
        return venues, srcs, with_ev

    def _verified(v: Venue, srcs: dict[int, set[str]]) -> bool:
        return ("google_places" in srcs.get(v.id, set())
                and v.business_status != "CLOSED_PERMANENTLY")

    def _dist_km(a: Venue, b: Venue) -> float:
        return _haversine_km(a.lat, a.lng, b.lat, b.lng)

    # regra 1: consolidacao por nome
    venues, srcs, _ = _snapshot()
    pids = _place_ids_by_venue(session)
    gone: set[int] = set()
    for i, a in enumerate(venues):
        if a.id in gone:
            continue
        for b in venues[i + 1:]:
            if b.id in gone or a.id in gone:
                continue
            if not (_verified(a, srcs) or _verified(b, srcs)):
                continue
            if _dist_km(a, b) > 0.03:
                continue
            sim = name_similarity(a.name, b.name)
            if sim < 0.60:
                continue
            distinct_pids = (a.id in pids and b.id in pids and pids[a.id] != pids[b.id])
            if sim < 0.70 or distinct_pids or _streets_differ(a.address, b.address):
                _queue_review(session, a, b, sim)
                out["review_queued"] += 1
                continue
            survivor, loser = _pick_survivor(a, b)
            merge_venues(session, survivor, loser, reference=reference)
            gone.add(loser.id)
            out["consolidated"] += 1

    # regra 2: supersessao de fantasmas (snapshot fresco: regra 1 mudou o banco)
    venues, srcs, with_ev = _snapshot()
    gone = set()
    for g in venues:
        if g.id in gone:
            continue
        gsrc = srcs.get(g.id, set())
        if not (len(gsrc) == 1 and next(iter(gsrc)) in ("ra", "osm")):
            continue
        if g.id in with_ev:
            continue                      # tem evento: nao e fantasma
        near30 = [v for v in venues
                  if v.id != g.id and v.id not in gone
                  and _verified(v, srcs) and _dist_km(g, v) <= 0.03]
        if len(near30) == 1:
            cand = near30[0]
            if _streets_differ(g.address, cand.address):
                # enderecos em ruas diferentes: vizinho vivo, nao fantasma
                # renomeado (caso Funilaria/Redoma) -> review, nao merge
                _queue_review(session, g, cand, name_similarity(g.name, cand.name))
                out["review_queued"] += 1
                continue
            merge_venues(session, cand, g, reference=reference)
            gone.add(g.id)
            out["superseded"] += 1
            continue
        near60 = [v for v in venues
                  if v.id != g.id and v.id not in gone
                  and _verified(v, srcs) and _dist_km(g, v) <= 0.06]
        if len(near30) >= 2 or near60:
            other = (near30 or near60)[0]
            _queue_review(session, g, other, name_similarity(g.name, other.name))
            out["review_queued"] += 1
        else:
            out["untouched"] += 1

    session.flush()
    return out


def main() -> None:
    from .config import GOOGLE_MAPS_API_KEY

    if not GOOGLE_MAPS_API_KEY:
        print("ERRO: defina GOOGLE_MAPS_API_KEY (Places API New + billing)")
        sys.exit(1)

    import truststore
    truststore.inject_into_ssl()  # Avast intercepta TLS (padrao do projeto)

    from .db import SessionLocal
    from .ingestion.places_client import PlacesClient

    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        client = PlacesClient(GOOGLE_MAPS_API_KEY)
        out = enrich_all(session, client, now=now)
        # commit intermediario: o enrichment e PAGO (Details); um erro no
        # reconcile nao pode rolar back os enriched_at (senao re-paga tudo)
        session.commit()
        rec = reconcile_venues(session, reference=now.date())
        session.commit()
        print("enrich:", out)
        print("reconcile:", rec)


if __name__ == "__main__":
    main()
