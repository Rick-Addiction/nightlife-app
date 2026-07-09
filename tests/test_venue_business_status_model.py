# tests/test_venue_business_status_model.py
from datetime import datetime, timezone

from nightlife.models import Venue


def test_venue_persiste_business_status_e_enriched_at(session):
    now = datetime.now(timezone.utc)
    v = Venue(name="Selva Club", business_status="OPERATIONAL", enriched_at=now)
    session.add(v)
    session.flush()
    got = session.get(Venue, v.id)
    assert got.business_status == "OPERATIONAL"
    assert got.enriched_at is not None
