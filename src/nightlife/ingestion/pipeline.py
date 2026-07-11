# src/nightlife/ingestion/pipeline.py
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.matching import VenueRef, match_venue
from ..extraction.base import ExtractedEvent
from ..extraction.freetext import extract_freetext_deterministic
from ..extraction.html_patterns import parse_html_patterns
from ..extraction.jsonld import parse_jsonld_events
from ..models import IngestionRun, Venue
from ..persistence.events_repo import upsert_event
from ..persistence.inputs import EventInput, SourceInfo, VenueInput
from ..persistence.organizers import get_or_create_organizer
from ..persistence.venues_repo import upsert_venue
from .base import RawEventPage, Source


def _extract_page(page: RawEventPage, reference: date) -> list[ExtractedEvent]:
    if page.kind == "jsonld":
        return parse_jsonld_events(page.content, source_url=page.source_url)
    if page.kind == "html":
        return parse_html_patterns(page.content, source_url=page.source_url)
    if page.kind == "freetext":
        return [extract_freetext_deterministic(page.content, reference=reference, source_url=page.source_url)]
    raise ValueError(f"kind de pagina desconhecido: {page.kind!r}")


def _resolve_venue(session: Session, venue_name: str | None) -> Venue | None:
    if not venue_name:
        return None
    existing = session.scalars(select(Venue)).all()
    refs = [VenueRef(v.id, v.name, v.address, v.lat, v.lng) for v in existing]
    m = match_venue(VenueRef(None, venue_name), refs)
    return session.get(Venue, m.venue.id) if m is not None else None


def venue_by_handle(session: Session, handle: str | None) -> Venue | None:
    """Venue dono do handle (fallback de ancoragem). So VENUES — organizer
    posta festa em casa alheia, ancorar nele erraria o lugar. Handle
    duplicado (venues ainda nao deduplicados): fica o de maior confianca."""
    if not handle:
        return None
    return session.scalars(
        select(Venue).where(Venue.instagram == handle)
        .order_by(Venue.confidence.desc(), Venue.id)
    ).first()


def run_ingestion(session: Session, source: Source, *, reference: date, label: str = "mock") -> IngestionRun:
    run = IngestionRun(source=label, status="running")
    session.add(run)
    session.flush()

    found = created = 0
    errors: list[str] = []

    try:
        raw_venues = list(source.venues())
        raw_pages = list(source.event_pages())
        raw_events = list(source.events())
    except Exception as exc:  # noqa: BLE001 — a fonte inteira falhou (rede/parse):
        # marca o run com erro e reporta, em vez de estourar traceback (spec OSM §7)
        run.status = "error"
        run.errors = f"fonte {label!r}: {exc}"
        run.finished_at = datetime.now(timezone.utc)
        session.flush()
        return run

    for rv in raw_venues:
        found += 1
        try:
            upsert_venue(
                session,
                VenueInput(name=rv.name, lat=rv.lat, lng=rv.lng, address=rv.address, category=rv.category),
                SourceInfo(source_type=rv.source_type, source_url=rv.source_url, raw_payload=rv.raw_payload),
                reference=reference,
            )
            created += 1
        except Exception as exc:  # noqa: BLE001 — registra e segue
            errors.append(f"venue {rv.name!r}: {exc}")

    for page in raw_pages:
        found += 1
        try:
            extracted = _extract_page(page, reference)
        except Exception as exc:  # noqa: BLE001 — extracao da pagina falhou
            errors.append(f"page {page.source_url!r} (extract): {exc}")
            continue
        for ev in extracted:
            if not ev.name:
                continue
            try:
                venue = _resolve_venue(session, ev.venue_name)
                upsert_event(
                    session,
                    EventInput(
                        name=ev.name, starts_at=ev.starts_at,
                        venue_id=venue.id if venue is not None else None,
                        venue_name=ev.venue_name, ticket_url=ev.ticket_url,
                        raw_fields=ev.raw,
                    ),
                    SourceInfo(source_type=page.source_type, source_url=page.source_url, raw_payload=page.content),
                    reference=reference,
                )
                created += 1
            except Exception as exc:  # noqa: BLE001 — registra o evento e segue
                errors.append(f"page {page.source_url!r} event {ev.name!r}: {exc}")

    for rev in raw_events:
        found += 1
        try:
            venue = None
            if rev.venue is not None:
                venue = upsert_venue(
                    session,
                    VenueInput(name=rev.venue.name, lat=rev.venue.lat, lng=rev.venue.lng,
                               address=rev.venue.address, category=rev.venue.category),
                    # URL ESTAVEL do venue (ex.: RA /clubs/ID), nao a do evento — senao
                    # cada evento vira um venue novo (a identidade por source_url do
                    # upsert_venue nunca reagrupa). No-op p/ Sympla (URLs coincidem).
                    SourceInfo(source_type=rev.source_type,
                               source_url=rev.venue.source_url or rev.source_url,
                               raw_payload=rev.raw_payload),
                    reference=reference,
                )
            elif rev.venue_name:
                # flyer da nome sem geo (e com typo): ancora no catalogo, nunca cria
                venue = _resolve_venue(session, rev.venue_name)
            anchored_by_handle = False
            if venue is None:
                # nome nao resolveu (ou nem veio): flyer postado pelo IG do
                # proprio venue ancora nele (Ciclo D-1)
                venue = venue_by_handle(session, rev.source_handle)
                anchored_by_handle = venue is not None
            organizer_id = None
            if rev.organizer_name:
                organizer_id = get_or_create_organizer(session, rev.organizer_name).id
            raw_fields = {"raw": rev.raw_payload}
            if anchored_by_handle:
                # trilha de evidencia (B6): distingue "ancorou pelo nome/geo" de
                # "ancorou so pelo handle de quem postou" pra auditoria futura.
                raw_fields["anchored_by"] = "ig_handle"
            upsert_event(
                session,
                EventInput(
                    name=rev.name, starts_at=rev.starts_at, ends_at=rev.ends_at,
                    venue_id=venue.id if venue is not None else None,
                    venue_name=rev.venue.name if rev.venue is not None else rev.venue_name,
                    organizer=rev.organizer_name, organizer_id=organizer_id,
                    genre=rev.genre, ticket_url=rev.ticket_url,
                    lineup_text=rev.lineup_text,
                    raw_fields=raw_fields,
                ),
                SourceInfo(source_type=rev.source_type, source_url=rev.source_url,
                           raw_payload=rev.raw_payload),
                reference=reference,
            )
            created += 1
        except Exception as exc:  # noqa: BLE001 — registra o evento e segue
            errors.append(f"structured event {rev.name!r}: {exc}")

    run.status = "finished"
    run.records_found = found
    run.records_created = created
    run.finished_at = datetime.now(timezone.utc)
    run.errors = "\n".join(errors) or None
    session.flush()
    return run
