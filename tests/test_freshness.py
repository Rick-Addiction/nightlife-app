# tests/test_freshness.py
from datetime import datetime, timedelta, timezone

from nightlife.domain.freshness import freshness_factor

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def test_fresh_within_30_days_is_full():
    assert freshness_factor(NOW - timedelta(days=10), NOW) == 1.0
    assert freshness_factor(NOW - timedelta(days=30), NOW) == 1.0
    assert freshness_factor(NOW, NOW) == 1.0


def test_linear_decay_then_floor():
    assert freshness_factor(NOW - timedelta(days=105), NOW) == 0.75  # meio caminho
    assert freshness_factor(NOW - timedelta(days=180), NOW) == 0.5
    assert freshness_factor(NOW - timedelta(days=400), NOW) == 0.5   # piso
