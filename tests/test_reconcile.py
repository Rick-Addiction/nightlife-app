from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue, VenueSource, Event, DedupeCandidate
from nightlife.enrich_places import reconcile_venues

REF = date(2026, 7, 9)


def _venue(session, name, lat, lng, sources=(), confidence=0, with_event=False):
    v = Venue(name=name, lat=lat, lng=lng, category="nightclub", confidence=confidence)
    session.add(v)
    session.flush()
    for stype, url in sources:
        session.add(VenueSource(venue_id=v.id, source_type=stype, source_url=url))
    if with_event:
        session.add(Event(name=f"Festa em {name}", venue_id=v.id))
    session.flush()
    return v


def test_consolidacao_funde_par_verificado_similar(session):
    # caso Kat Klub: RA "Kat Klub Sao Paulo" + Places "Kat Klub" a ~10m, 0.615+0.1 >= 0.70
    ra = _venue(session, "Kat Klub Sao Paulo", -23.55202, -46.65170,
                sources=[("ra", "https://ra.co/clubs/2")], confidence=40)
    gp = _venue(session, "Kat Klub", -23.55210, -46.65175,
                sources=[("google_places", "PID_KAT")], confidence=30)
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["consolidated"] == 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    survivor = session.scalars(select(Venue)).one()
    srcs = {s.source_type for s in session.scalars(select(VenueSource))}
    assert srcs == {"ra", "google_places"}     # evidencias unificadas
    assert survivor.id == ra.id                # _pick_survivor: maior confianca


def test_consolidacao_ignora_par_sem_lado_verificado(session):
    _venue(session, "Bar Alfa", -23.55, -46.65, sources=[("ra", "u1")])
    _venue(session, "Bar Alfa", -23.5501, -46.6501, sources=[("osm", "u2")])
    out = reconcile_venues(session, reference=REF)
    assert out["consolidated"] == 0
    assert session.scalar(select(func.count()).select_from(Venue)) == 2


def test_supersessao_funde_fantasma_ra_no_verificado(session):
    # caso Inferno->Selva: nomes DIFERENTES (sim < 0.70), <=30m, fantasma so-RA
    selva = _venue(session, "Selva Club", -23.55157, -46.65077,
                   sources=[("google_places", "PID_SELVA")], confidence=30)
    inferno = _venue(session, "Inferno Club", -23.55170, -46.65072,
                     sources=[("ra", "https://ra.co/clubs/28883")], confidence=0)
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["superseded"] == 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    survivor = session.scalars(select(Venue)).one()
    assert survivor.name == "Selva Club"
    urls = {s.source_url for s in session.scalars(select(VenueSource))}
    assert "https://ra.co/clubs/28883" in urls   # identidade RA migrou


def test_supersessao_funde_fantasma_osm(session):
    # caso Beco 203 -> Kat Klub (fantasma so-OSM)
    kat = _venue(session, "Kat Klub", -23.55202, -46.65170,
                 sources=[("google_places", "PID_KAT")], confidence=30)
    _venue(session, "Beco 203", -23.55215, -46.65180,
           sources=[("osm", "https://osm.org/node/1")], confidence=20)
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["superseded"] == 1
    assert session.scalars(select(Venue)).one().name == "Kat Klub"


def test_supersessao_dois_candidatos_vira_review(session):
    # nomes DISSIMILARES de proposito: senao a regra 1 (consolidacao) fundiria
    # os dois verificados antes da regra 2 rodar
    _venue(session, "Selva Club", -23.55000, -46.65000,
           sources=[("google_places", "PA")], confidence=30)
    _venue(session, "Outs Club", -23.55010, -46.65010,
           sources=[("google_places", "PB")], confidence=30)
    _venue(session, "Fantasma", -23.55005, -46.65005,
           sources=[("ra", "u")], confidence=0)
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["superseded"] == 0 and out["review_queued"] == 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 3
    assert session.scalar(select(func.count()).select_from(DedupeCandidate)) == 1


def test_supersessao_30_a_60m_vira_review(session):
    _venue(session, "Verificado", -23.55000, -46.65000,
           sources=[("google_places", "P1")], confidence=30)
    # ~44m ao sul (0.0004 graus de lat)
    _venue(session, "Fantasma Longe", -23.55040, -46.65000,
           sources=[("ra", "u")], confidence=0)
    out = reconcile_venues(session, reference=REF)
    assert out["superseded"] == 0 and out["review_queued"] == 1


def test_fantasma_com_evento_e_intocado(session):
    _venue(session, "Verificado", -23.55000, -46.65000,
           sources=[("google_places", "P1")], confidence=30)
    _venue(session, "Com Evento", -23.55005, -46.65005,
           sources=[("ra", "u")], confidence=0, with_event=True)
    out = reconcile_venues(session, reference=REF)
    assert out["superseded"] == 0 and out["review_queued"] == 0
    assert session.scalar(select(func.count()).select_from(Venue)) == 2


def test_reconcile_e_idempotente(session):
    _venue(session, "Selva Club", -23.55157, -46.65077,
           sources=[("google_places", "PID_SELVA")], confidence=30)
    _venue(session, "Inferno Club", -23.55170, -46.65072,
           sources=[("ra", "u")], confidence=0)
    reconcile_venues(session, reference=REF)
    session.flush()
    out2 = reconcile_venues(session, reference=REF)
    assert out2["superseded"] == 0 and out2["consolidated"] == 0
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
