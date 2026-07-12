# tests/test_venues_repo.py
from datetime import date

from sqlalchemy import select

from nightlife.models import DedupeCandidate, Venue, VenueSource
from nightlife.persistence.inputs import SourceInfo, VenueInput
from nightlife.persistence.venues_repo import upsert_venue

REF = date(2026, 6, 1)


def _src(stype="google_places", url="http://x"):
    return SourceInfo(source_type=stype, source_url=url,
                      raw_payload='{"k":1}', extracted_fields={"k": 1})


def test_creates_new_venue_with_score_and_evidence(session):
    v = upsert_venue(
        session,
        VenueInput(name="Lab Club", lat=-23.561, lng=-46.656, address="R. X", category="nightclub"),
        _src("google_places", "http://g"),
        reference=REF,
    )
    assert v.id is not None
    assert v.confidence == 30  # evidencia acumulada: so google_places
    srcs = session.scalars(select(VenueSource)).all()
    assert len(srcs) == 1 and srcs[0].confidence_contribution == 30


def test_auto_merge_accumulates_confidence(session):
    upsert_venue(session, VenueInput(name="Lab Club", lat=-23.561, lng=-46.656),
                 _src("google_places", "http://g"), reference=REF)
    v = upsert_venue(session, VenueInput(name="lab club", lat=-23.5611, lng=-46.6561),
                     _src("osm", "https://osm.org/1"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 1      # nao duplicou
    assert len(session.scalars(select(VenueSource)).all()) == 2  # duas evidencias
    assert v.confidence == 50  # places(30) + osm(20) ACUMULADOS


def test_rerun_same_source_is_idempotent(session):
    upsert_venue(session, VenueInput(name="Lab Club"), _src("osm", "https://osm.org/1"), reference=REF)
    v = upsert_venue(session, VenueInput(name="Lab Club"), _src("osm", "https://osm.org/1"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 1
    assert len(session.scalars(select(VenueSource)).all()) == 1  # evidencia nao duplica
    assert v.confidence == 20


def test_distinct_names_create_two_venues(session):
    upsert_venue(session, VenueInput(name="Lab Club"), _src(), reference=REF)
    upsert_venue(session, VenueInput(name="Trackers"), _src(url="http://y"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 2
    assert session.scalars(select(DedupeCandidate)).all() == []


def test_same_name_far_apart_is_distinct_not_merged(session):
    # mesmo nome a ~7km: filial/xara, nao duplicata — nem merge, nem review
    upsert_venue(session, VenueInput(name="Villa Country", lat=-23.50, lng=-46.60),
                 _src(url="http://a"), reference=REF)
    upsert_venue(session, VenueInput(name="Villa Country", lat=-23.55, lng=-46.65),
                 _src(url="http://b"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 2
    assert session.scalars(select(DedupeCandidate)).all() == []


def test_mid_similarity_creates_new_plus_review_candidate(session):
    # "Audio SP" x "Audio Club" -> similaridade ~0.77 (faixa 0.70-0.85):
    # cria venue novo E registra candidato de revisao, sem merge automatico
    upsert_venue(session, VenueInput(name="Audio Club"), _src(url="http://a"), reference=REF)
    upsert_venue(session, VenueInput(name="Audio SP"), _src(url="http://b"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 2
    cands = session.scalars(select(DedupeCandidate)).all()
    assert len(cands) == 1
    assert cands[0].kind == "venue" and cands[0].decision == "review"


def test_geoless_mesmo_source_url_e_idempotente(session):
    # venue SEM geo, re-ingerido com o MESMO (source_type, source_url) -> 1 venue
    upsert_venue(session, VenueInput(name="D-EDGE"), _src("ra", "https://ra.co/clubs/4973"), reference=REF)
    upsert_venue(session, VenueInput(name="D-EDGE"), _src("ra", "https://ra.co/clubs/4973"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 1
    assert len(session.scalars(select(VenueSource)).all()) == 1


def test_geoless_nomes_iguais_fontes_diferentes_viram_review(session):
    # "Club Mono" e "Mono Club" normalizam p/ "mono" (score 1.0), mas SEM geo e de
    # fontes diferentes -> review (cria 2o venue), NUNCA funde
    upsert_venue(session, VenueInput(name="Club Mono"), _src("ra", "https://ra.co/clubs/1"), reference=REF)
    upsert_venue(session, VenueInput(name="Mono Club"), _src("osm", "https://osm.org/9"), reference=REF)
    assert len(session.scalars(select(Venue)).all()) == 2          # nao fundiu
    cands = session.scalars(select(DedupeCandidate)).all()
    assert len(cands) == 1 and cands[0].decision == "review"


def test_place_id_distinto_veta_auto_merge(session):
    # CASO SUPRA (smoke E-1): Supra Club Augusta a 24m do Casarao Augusta,
    # score 0.89 -> auto_merge fundia dois CLUBES DIFERENTES. Veto da
    # reconciliacao do Ciclo A (place_ids distintos = Google diz que sao dois
    # lugares) portado pro ingest: vira review, nunca funde.
    casarao = upsert_venue(
        session, VenueInput(name="Casarão Augusta", lat=-23.5525607, lng=-46.653397,
                            address="R. Augusta, 791 - Consolação, São Paulo"),
        _src("google_places", "ChIJ_CASARAO"), reference=REF)
    supra = upsert_venue(
        session, VenueInput(name="Supra Club Augusta", lat=-23.5525337, lng=-46.6531663,
                            address="R. Augusta, 765 - Consolação, São Paulo"),
        _src("google_places", "ChIJ_SUPRA"), reference=REF)
    assert supra.id != casarao.id            # NAO fundiu
    from nightlife.models import DedupeCandidate
    dc = session.query(DedupeCandidate).filter_by(kind="venue").all()
    assert any({d.a_id, d.b_id} == {supra.id, casarao.id} for d in dc)  # foi pra review


def test_veto_nao_atrapalha_auto_merge_sem_conflito_de_place_id(session):
    # mesmo lugar visto por OSM e depois por Places: sem place_id no alvo,
    # auto_merge continua valendo (comportamento atual preservado)
    a = upsert_venue(session, VenueInput(name="Lab Club", lat=-23.561, lng=-46.656),
                     _src("osm", "https://osm.org/lab"), reference=REF)
    b = upsert_venue(session, VenueInput(name="lab club", lat=-23.5611, lng=-46.6561),
                     _src("google_places", "ChIJ_LAB"), reference=REF)
    assert b.id == a.id
