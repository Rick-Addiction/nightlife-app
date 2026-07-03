# src/nightlife/persistence/evidence.py
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EventSource, VenueSource
from ._utils import payload_hash
from .inputs import SourceInfo


def _record(session: Session, model, fk_col, entity_id: int, source: SourceInfo,
            contribution: int):
    """Upsert de evidencia por chave (entidade, source_type, source_url).

    Re-executar a mesma fonte atualiza last_seen_at (e o payload, se mudou)
    em vez de inserir linha duplicada — spec §3 'reprocessar so o que mudou'.
    Comparar coluna com None vira IS NULL no SQLAlchemy, entao url ausente
    tambem funciona como chave.
    """
    row = session.scalars(
        select(model).where(
            fk_col == entity_id,
            model.source_type == source.source_type,
            model.source_url == source.source_url,
        )
    ).first()
    now = datetime.now(timezone.utc)
    new_hash = payload_hash(source.raw_payload)
    if row is not None:
        row.fetched_at = now
        row.last_seen_at = now
        if row.raw_payload_hash != new_hash:
            row.raw_payload_hash = new_hash
            row.extracted_fields = source.extracted_fields
        row.confidence_contribution = contribution
    else:
        row = model(
            source_type=source.source_type,
            source_url=source.source_url,
            raw_payload_hash=new_hash,
            extracted_fields=source.extracted_fields,
            confidence_contribution=contribution,
        )
        setattr(row, fk_col.key, entity_id)
        session.add(row)
    # flush: a evidencia precisa estar visivel para o recompute que vem a seguir
    # (e para o proximo lookup em sessoes com autoflush=False, como a SessionLocal)
    session.flush()
    return row


def record_venue_evidence(session: Session, venue_id: int, source: SourceInfo,
                          *, contribution: int) -> VenueSource:
    return _record(session, VenueSource, VenueSource.venue_id, venue_id, source, contribution)


def record_event_evidence(session: Session, event_id: int, source: SourceInfo,
                          *, contribution: int) -> EventSource:
    return _record(session, EventSource, EventSource.event_id, event_id, source, contribution)
