# tests/test_evidence.py
from sqlalchemy import select

from nightlife.models import Event, EventSource, Venue, VenueSource
from nightlife.persistence.evidence import record_event_evidence, record_venue_evidence
from nightlife.persistence.inputs import SourceInfo


def _src(payload='{"a":1}', url="https://osm.org/node/1"):
    return SourceInfo(source_type="osm", source_url=url, raw_payload=payload,
                      extracted_fields={"p": payload})


def test_venue_evidence_is_idempotent(session):
    v = Venue(name="Lab Club")
    session.add(v)
    session.flush()

    record_venue_evidence(session, v.id, _src(), contribution=20)
    record_venue_evidence(session, v.id, _src(), contribution=20)  # mesma fonte de novo
    rows = session.scalars(select(VenueSource)).all()
    assert len(rows) == 1  # atualizou, nao duplicou
    assert rows[0].confidence_contribution == 20

    # payload mudou -> hash e extracted_fields atualizam, ainda 1 linha
    old_hash = rows[0].raw_payload_hash
    record_venue_evidence(session, v.id, _src(payload='{"a":2}'), contribution=20)
    rows = session.scalars(select(VenueSource)).all()
    assert len(rows) == 1 and rows[0].raw_payload_hash != old_hash

    # source_url diferente -> linha nova
    record_venue_evidence(session, v.id, _src(url="https://osm.org/node/2"), contribution=20)
    assert len(session.scalars(select(VenueSource)).all()) == 2


def test_event_evidence_idempotent_with_null_url(session):
    e = Event(name="Festa X")
    session.add(e)
    session.flush()
    s = SourceInfo(source_type="manual", source_url=None, raw_payload="x", extracted_fields={})
    record_event_evidence(session, e.id, s, contribution=0)
    record_event_evidence(session, e.id, s, contribution=0)
    assert len(session.scalars(select(EventSource)).all()) == 1  # NULL url tambem e chave
