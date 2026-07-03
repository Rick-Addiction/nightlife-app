# tests/test_confidence.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nightlife.models import Event, Venue, VerificationLog
from nightlife.persistence.confidence import (
    recompute_event_confidence,
    recompute_venue_confidence,
)
from nightlife.persistence.evidence import record_event_evidence, record_venue_evidence
from nightlife.persistence.inputs import SourceInfo

SP = ZoneInfo("America/Sao_Paulo")
REF = date(2026, 6, 1)


def _src(stype, url):
    return SourceInfo(source_type=stype, source_url=url, raw_payload="p", extracted_fields={})


def test_venue_confidence_accumulates_and_sees_future_event(session):
    v = Venue(name="Lab Club")
    session.add(v)
    session.flush()

    record_venue_evidence(session, v.id, _src("osm", "https://osm.org/1"), contribution=20)
    assert recompute_venue_confidence(session, v, reference=REF) == 20

    record_venue_evidence(session, v.id, _src("google_places", "https://g.co/1"), contribution=30)
    assert recompute_venue_confidence(session, v, reference=REF) == 50  # acumula, nao max()

    # evento futuro linkado -> +15 (a promessa do spec §7 que estava morta)
    session.add(Event(name="Festa", venue_id=v.id,
                      starts_at=datetime(2026, 6, 13, 23, 0, tzinfo=SP)))
    session.flush()
    assert recompute_venue_confidence(session, v, reference=REF) == 65

    logs = session.scalars(select(VerificationLog)).all()
    assert len(logs) == 3  # cada mudanca de score gera trilha


def test_event_multisource_bonus_and_recompute_down(session):
    v = Venue(name="Audio")
    session.add(v)
    session.flush()
    e = Event(name="Mamba Negra", venue_id=v.id,
              starts_at=datetime(2026, 6, 13, 23, 0, tzinfo=SP))
    session.add(e)
    session.flush()

    record_event_evidence(session, e.id, _src("ticketing", "https://t/1"), contribution=25)
    # future 20 + venue 20 + ticketing 25, 1 fonte
    assert recompute_event_confidence(session, e, reference=REF) == 65

    record_event_evidence(session, e.id, _src("instagram", "https://ig/1"), contribution=0)
    # 2 source_types distintos -> +20 multi-fonte
    assert recompute_event_confidence(session, e, reference=REF) == 85

    e.status = "cancelled"
    # recompute pode DESCER: 85 - 50 (cancelado) = 35
    assert recompute_event_confidence(session, e, reference=REF) == 35


def test_future_past_uses_sao_paulo_day(session):
    from datetime import timezone

    from nightlife.persistence.confidence import event_signals_from_evidence

    v = Venue(name="X")
    session.add(v)
    session.flush()
    # sabado 06/06/2026 23:00 em SP == domingo 07/06 02:00 UTC
    e = Event(name="Madrugada", venue_id=v.id,
              starts_at=datetime(2026, 6, 7, 2, 0, tzinfo=timezone.utc))
    session.add(e)
    session.flush()
    record_event_evidence(session, e.id, _src("ticketing", "https://t/x"), contribution=25)

    # referencia = domingo 07/06: no dia SP o evento foi SABADO -> passado
    sig = event_signals_from_evidence(session, e, reference=date(2026, 6, 7))
    assert sig.past_date is True and sig.future_date is False
    # referencia = sabado 06/06: mesmo dia SP -> futuro
    sig2 = event_signals_from_evidence(session, e, reference=date(2026, 6, 6))
    assert sig2.future_date is True and sig2.past_date is False
