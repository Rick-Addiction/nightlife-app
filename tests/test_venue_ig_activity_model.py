# tests/test_venue_ig_activity_model.py
from datetime import datetime, timezone

from nightlife.models import Venue


def test_venue_persiste_ig_last_post_at(session):
    ts = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    v = Venue(name="Selva Club", ig_last_post_at=ts)
    session.add(v)
    session.flush()
    assert session.get(Venue, v.id).ig_last_post_at == ts
