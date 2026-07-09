from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue, VenueSource, Event, DedupeCandidate
from nightlife.enrich_places import reconcile_venues

REF = date(2026, 7, 9)


def _venue(session, name, lat, lng, sources=(), confidence=0, with_event=False, address=None):
    v = Venue(name=name, lat=lat, lng=lng, category="nightclub", confidence=confidence,
              address=address)
    session.add(v)
    session.flush()
    for stype, url in sources:
        session.add(VenueSource(venue_id=v.id, source_type=stype, source_url=url))
    if with_event:
        session.add(Event(name=f"Festa em {name}", venue_id=v.id))
    session.flush()
    return v


def test_consolidacao_funde_par_verificado_similar(session):
    # similaridade CRUA >= 0.70 ("Kat Klub SP" vs "Kat Klub" = 0.842), <=30m,
    # um lado verificado, sem conflito de rua -> funde
    ra = _venue(session, "Kat Klub SP", -23.55202, -46.65170,
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


def test_consolidacao_faixa_ambigua_vira_review(session):
    # faixa 0.60-0.70 crua e INDISTINGUIVEL (Kat Klub 0.615 = mesmo clube;
    # Funilaria/Redoma 0.621 = clubes DIFERENTES, medido em producao)
    # -> review, nunca auto-merge. with_event: como na producao (o RA Kat Klub
    # tem evento), o venue nao e fantasma — isola a regra 1 da supersessao.
    _venue(session, "Kat Klub Sao Paulo", -23.55202, -46.65170,
           sources=[("ra", "https://ra.co/clubs/2")], confidence=40, with_event=True)
    _venue(session, "Kat Klub", -23.55210, -46.65175,
           sources=[("google_places", "PID_KAT")], confidence=30)
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["consolidated"] == 0 and out["review_queued"] >= 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 2
    assert session.scalar(select(func.count()).select_from(DedupeCandidate)) == 1


def test_consolidacao_dois_place_ids_distintos_vira_review(session):
    # o Google diz que sao DOIS negocios (place_ids diferentes): 0.714 cru
    # ("Kibixiga Show" vs "Que Bexiga Show"), mas nunca auto-merge
    _venue(session, "Kibixiga Show", -23.55000, -46.65000,
           sources=[("google_places", "PID_A")], confidence=30)
    _venue(session, "Que Bexiga Show", -23.55005, -46.65005,
           sources=[("google_places", "PID_B")], confidence=30)
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["consolidated"] == 0 and out["review_queued"] >= 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 2


def test_consolidacao_ruas_diferentes_vira_review(session):
    # nomes identicos pos-normalizacao (1.0) mas enderecos em RUAS diferentes:
    # lugares distintos -> review, nao merge
    _venue(session, "Fugaz Bar", -23.55000, -46.65000,
           sources=[("ra", "u1")], confidence=20,
           address="Rua Rui Barbosa, 572; Sao Paulo")
    _venue(session, "Fugaz Club", -23.55005, -46.65005,
           sources=[("google_places", "P1")], confidence=30,
           address="Rua Treze de Maio, 825 - Bela Vista, Sao Paulo")
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["consolidated"] == 0 and out["review_queued"] >= 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 2


def test_consolidacao_ignora_par_sem_lado_verificado(session):
    _venue(session, "Bar Alfa", -23.55, -46.65, sources=[("ra", "u1")])
    _venue(session, "Bar Alfa", -23.5501, -46.6501, sources=[("osm", "u2")])
    out = reconcile_venues(session, reference=REF)
    assert out["consolidated"] == 0
    assert session.scalar(select(func.count()).select_from(Venue)) == 2


def test_supersessao_funde_fantasma_ra_no_verificado(session):
    # caso Inferno->Selva: nomes DIFERENTES (sim < 0.70), <=30m, fantasma so-RA,
    # MESMA rua nos enderecos (nao dispara o veto)
    selva = _venue(session, "Selva Club", -23.55157, -46.65077,
                   sources=[("google_places", "PID_SELVA")], confidence=30,
                   address="R. Augusta, 501 - Consolacao, Sao Paulo")
    inferno = _venue(session, "Inferno Club", -23.55170, -46.65072,
                     sources=[("ra", "https://ra.co/clubs/28883")], confidence=0,
                     address="R. Augusta, 501; Sao Paulo, 01305-000; Brazil")
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


def test_supersessao_ruas_diferentes_vira_review(session):
    # caso Funilaria/Redoma (medido em producao): fantasma a 17m de um
    # verificado, mas em RUA diferente -> vizinho vivo, nao fantasma renomeado
    # -> review, nao merge
    _venue(session, "Redoma Bixiga", -23.55000, -46.65000,
           sources=[("google_places", "P1")], confidence=30,
           address="R. Treze de Maio, 825 - Bela Vista, Sao Paulo")
    _venue(session, "Funilaria Bixiga", -23.55015, -46.65005,
           sources=[("ra", "https://ra.co/clubs/248292")], confidence=0,
           address="R. Rui Barbosa, 572; Sao Paulo")
    out = reconcile_venues(session, reference=REF)
    session.flush()
    assert out["superseded"] == 0 and out["review_queued"] >= 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 2
    # par unico na fila mesmo sendo tocado pelas duas regras
    assert session.scalar(select(func.count()).select_from(DedupeCandidate)) == 1


def test_venue_meio_geocodado_nao_quebra_reconcile(session):
    # lat sem lng (meia-geocodificacao) nao pode estourar TypeError no haversine
    v = Venue(name="Meio Geo", lat=-23.55, lng=None, category="nightclub")
    session.add(v)
    session.flush()
    _venue(session, "Normal Club", -23.55000, -46.65000,
           sources=[("google_places", "P1")], confidence=30)
    out = reconcile_venues(session, reference=REF)   # nao explode
    assert out["consolidated"] == 0


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
