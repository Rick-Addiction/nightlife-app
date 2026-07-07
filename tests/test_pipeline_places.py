# tests/test_pipeline_places.py
from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue, VenueSource
from nightlife.ingestion.base import RawVenue
from nightlife.ingestion.mock_source import MockSource
from nightlife.ingestion.pipeline import run_ingestion

REF = date(2026, 6, 1)


def _places_venue(name, pid, lat, lng):
    return RawVenue(name=name, source_type="google_places", lat=lat, lng=lng,
                    address="Rua Augusta, 500", category="nightclub", source_url=pid)


def test_places_venue_funde_com_existente_proximo(session):
    # ja existe "Club Aloka" (ex.: veio do RA) com geo; o Places traz "Aloka Club"
    # no mesmo lugar -> auto_merge (1 venue), place_id vira evidencia google_places
    existing = Venue(name="Club Aloka", lat=-23.5550, lng=-46.6620, category="nightclub")
    session.add(existing)
    session.flush()
    rv = _places_venue("Aloka Club", "PID_ALOKA", -23.5551, -46.6621)
    run_ingestion(session, MockSource([rv], []), reference=REF, label="places")
    session.flush()

    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    src = session.scalars(select(VenueSource).where(
        VenueSource.source_type == "google_places", VenueSource.source_url == "PID_ALOKA")).first()
    assert src is not None and src.venue_id == existing.id


def test_places_venue_novo_e_criado(session):
    rv = _places_venue("Supra Club Augusta", "PID_SUPRA", -23.5545, -46.6620)
    run_ingestion(session, MockSource([rv], []), reference=REF, label="places")
    session.flush()
    v = session.scalars(select(Venue).where(Venue.name == "Supra Club Augusta")).one()
    assert v.category == "nightclub" and v.lat == -23.5545


def test_places_reingest_mesmo_place_id_e_idempotente(session):
    rv = _places_venue("Supra Club Augusta", "PID_SUPRA", -23.5545, -46.6620)
    run_ingestion(session, MockSource([rv], []), reference=REF, label="places")
    session.flush()
    run_ingestion(session, MockSource([rv], []), reference=REF, label="places")
    session.flush()
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    # uma unica linha de evidencia para o place_id
    n = session.scalar(select(func.count()).select_from(VenueSource).where(
        VenueSource.source_url == "PID_SUPRA"))
    assert n == 1
