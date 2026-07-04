# tests/test_flyer.py
from datetime import date

from nightlife.extraction.flyer import FlyerExtraction, flyer_to_raw_event

REF = date(2026, 6, 1)

GOOD = {
    "event_name": "MAMBA NEGRA",
    "date_text": "SEX 13/06 23h",
    "venue_name": "Lab Club",
    "organizer": "Mamba Org",
    "lineup": ["DJ A", "DJ B"],
    "price_text": "R$ 60",
    "ticket_url": "https://shotgun.live/mamba",
    "instagram_handle": "@mambanegra",
    "quotes": {"event_name": "MAMBA NEGRA", "date_text": "SEX 13/06 23h",
               "venue_name": "LAB CLUB", "organizer": "por MAMBA",
               "ticket_url": "shotgun.live/mamba"},
    "confidence": {"event_name": 0.95, "date_text": 0.9, "venue_name": 0.9,
                   "organizer": 0.6, "ticket_url": 0.8},
}


def test_adjusted_confidence_halves_fields_without_quote():
    ext = FlyerExtraction.model_validate({
        **GOOD,
        "quotes": {"event_name": "MAMBA NEGRA"},  # so event_name tem quote
    })
    adj = ext.adjusted_confidence()
    assert adj["event_name"] == 0.95          # com quote: intacto
    assert adj["date_text"] == 0.45           # sem quote: cortado pela metade
    assert adj["venue_name"] == 0.45


def test_flyer_to_raw_event_maps_and_parses_date():
    ext = FlyerExtraction.model_validate(GOOD)
    rev = flyer_to_raw_event(ext, "abc123", reference=REF)
    assert rev is not None
    assert rev.name == "MAMBA NEGRA"
    assert rev.source_type == "vision_flyer"
    # data parseada pelo NOSSO dates_ptbr, nao pelo modelo
    assert rev.starts_at is not None
    assert (rev.starts_at.day, rev.starts_at.hour) == (13, 23)
    assert rev.venue_name == "Lab Club" and rev.venue is None  # ancora, nao cria
    assert rev.organizer_name == "Mamba Org"
    assert rev.lineup_text == "DJ A, DJ B"
    assert rev.ticket_url == "https://shotgun.live/mamba"
    assert rev.source_url == "flyer:abc123"


def test_flyer_to_raw_event_guards():
    # sem event_name -> nao vira evento
    ext = FlyerExtraction.model_validate({**GOOD, "event_name": None})
    assert flyer_to_raw_event(ext, "x", reference=REF) is None
    # link generico (linktree) NAO vira ticket_url (quebraria o dedupe)
    ext2 = FlyerExtraction.model_validate({**GOOD, "ticket_url": "https://linktr.ee/clubx"})
    rev2 = flyer_to_raw_event(ext2, "x", reference=REF)
    assert rev2.ticket_url is None
