from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from nightlife.models import Venue, VenueSource, VerificationLog
from nightlife.ingestion.places_client import PlaceDetails
from nightlife.enrich_places import enrich_all

NOW = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)


class FakeDetailsClient:
    """place_details por place_id; conta chamadas."""
    def __init__(self, table):
        self.table = table          # place_id -> PlaceDetails | None
        self.calls = 0

    def place_details(self, place_id):
        self.calls += 1
        return self.table.get(place_id)


def _gp_venue(session, name, pid, **kw):
    v = Venue(name=name, lat=-23.5, lng=-46.6, category="nightclub", **kw)
    session.add(v)
    session.flush()
    session.add(VenueSource(venue_id=v.id, source_type="google_places", source_url=pid))
    session.flush()
    return v


def test_enrich_renomeia_com_trilha(session):
    v = _gp_venue(session, "Inferno Club", "PID_SELVA")
    client = FakeDetailsClient({"PID_SELVA": PlaceDetails(
        name="Selva Club", business_status="OPERATIONAL", website="https://selva.club/")})
    out = enrich_all(session, client, now=NOW)
    session.flush()
    assert v.name == "Selva Club"
    assert v.website == "https://selva.club/"
    assert v.business_status == "OPERATIONAL" and v.status == "operational"
    assert v.enriched_at == NOW
    assert out["renamed"] == 1 and out["enriched"] == 1
    logs = session.scalars(select(VerificationLog).where(
        VerificationLog.entity_id == v.id, VerificationLog.entity_type == "venue")).all()
    assert any("rename" in (lg.note or "") and "Selva Club" in lg.note for lg in logs)


def test_enrich_mapeia_closed_permanently(session):
    v = _gp_venue(session, "Morto Club", "PID_DEAD")
    client = FakeDetailsClient({"PID_DEAD": PlaceDetails(
        name="Morto Club", business_status="CLOSED_PERMANENTLY", website=None)})
    out = enrich_all(session, client, now=NOW)
    session.flush()
    assert v.status == "permanently_closed" and v.business_status == "CLOSED_PERMANENTLY"
    assert out["closed_perm"] == 1 and out["renamed"] == 0


def test_enrich_cache_30d_nao_rechama(session):
    v = _gp_venue(session, "Ja Enriquecido", "PID_X",
                  enriched_at=NOW - timedelta(days=5))
    client = FakeDetailsClient({"PID_X": PlaceDetails(name="Novo Nome", business_status=None, website=None)})
    out = enrich_all(session, client, now=NOW)
    assert client.calls == 0 and out["skipped_cached"] == 1
    assert v.name == "Ja Enriquecido"           # intocado


def test_enrich_erro_nao_grava_enriched_at(session):
    v = _gp_venue(session, "Erro Club", "PID_ERR")
    client = FakeDetailsClient({"PID_ERR": None})   # Details falhou (retentavel)
    out = enrich_all(session, client, now=NOW)
    assert out["errors"] == 1
    assert v.enriched_at is None                # retenta no proximo run


def test_enrich_ignora_venue_sem_place_id(session):
    v = Venue(name="So RA", lat=-23.5, lng=-46.6)
    session.add(v)
    session.flush()
    session.add(VenueSource(venue_id=v.id, source_type="ra", source_url="https://ra.co/clubs/1"))
    session.flush()
    client = FakeDetailsClient({})
    enrich_all(session, client, now=NOW)
    assert client.calls == 0
