from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue, VenueSource, Event, DedupeCandidate
from nightlife.persistence.venue_merge import merge_venues
from nightlife.persistence.venue_merge import rededup_geocoded

REF = date(2026, 6, 1)


def _venue(session, name, **kw):
    v = Venue(name=name, **kw)
    session.add(v)
    session.flush()
    return v


def test_merge_preserva_is_monitored_do_loser(session):
    # flag setada pelo usuario nao pode se perder quando o monitorado e o loser
    survivor = _venue(session, "Selva Club", lat=-23.55, lng=-46.65, is_monitored=False)
    loser = _venue(session, "Inferno Club", lat=-23.551, lng=-46.651, is_monitored=True)
    merge_venues(session, survivor, loser, reference=REF)
    session.flush()
    assert survivor.is_monitored is True


def test_merge_move_evento_e_source_e_apaga_loser(session):
    survivor = _venue(session, "Mundo Pensante", lat=-23.55, lng=-46.63)
    loser = _venue(session, "Mundo Pensante", lat=-23.551, lng=-46.631)
    session.add(VenueSource(venue_id=loser.id, source_type="ra", source_url="https://ra.co/clubs/9"))
    ev = Event(name="Festa X", venue_id=loser.id)
    session.add(ev)
    session.flush()
    loser_id = loser.id

    merge_venues(session, survivor, loser, reference=REF)
    session.flush()

    assert session.get(Venue, loser_id) is None            # loser apagado
    assert session.get(Event, ev.id).venue_id == survivor.id  # evento movido
    moved = session.scalars(
        select(VenueSource).where(VenueSource.venue_id == survivor.id)
    ).all()
    assert any(s.source_type == "ra" and s.source_url == "https://ra.co/clubs/9" for s in moved)


def test_merge_nao_duplica_evidencia_igual(session):
    survivor = _venue(session, "D-Edge", lat=-23.5, lng=-46.6)
    loser = _venue(session, "D-Edge", lat=-23.5, lng=-46.6)
    # mesma evidencia (source_type, source_url) nos dois
    session.add(VenueSource(venue_id=survivor.id, source_type="ra", source_url="https://ra.co/clubs/1"))
    session.add(VenueSource(venue_id=loser.id, source_type="ra", source_url="https://ra.co/clubs/1"))
    session.flush()

    merge_venues(session, survivor, loser, reference=REF)
    session.flush()

    rows = session.scalars(
        select(VenueSource).where(
            VenueSource.venue_id == survivor.id,
            VenueSource.source_type == "ra",
            VenueSource.source_url == "https://ra.co/clubs/1",
        )
    ).all()
    assert len(rows) == 1  # nao virou linha dupla


def test_merge_registra_verification_log(session):
    # merge e irreversivel: precisa deixar trilha do que fundiu em quem
    from nightlife.models import VerificationLog
    survivor = _venue(session, "Cine Joia", lat=-23.55, lng=-46.63)
    loser = _venue(session, "Cine Joia", lat=-23.55, lng=-46.63)
    loser_id = loser.id
    merge_venues(session, survivor, loser, reference=REF)
    session.flush()
    logs = session.scalars(
        select(VerificationLog).where(VerificationLog.entity_type == "venue")
    ).all()
    assert any(str(loser_id) in (lg.note or "") and lg.entity_id == survivor.id
               for lg in logs)


def test_merge_preenche_lacunas_e_limpa_dedupe_candidate(session):
    survivor = _venue(session, "Selva", lat=-23.5, lng=-46.6)   # sem address
    loser = _venue(session, "Selva", lat=-23.5, lng=-46.6, address="Rua Augusta, 100", instagram="selvasp")
    session.add(DedupeCandidate(kind="venue", a_id=survivor.id, b_id=loser.id,
                                similarity_score=0.9, decision="review"))
    session.flush()
    loser_id = loser.id

    merge_venues(session, survivor, loser, reference=REF)
    session.flush()

    assert survivor.address == "Rua Augusta, 100"   # lacuna preenchida do loser
    assert survivor.instagram == "selvasp"
    remaining = session.scalars(
        select(DedupeCandidate).where(
            (DedupeCandidate.a_id == loser_id) | (DedupeCandidate.b_id == loser_id)
        )
    ).all()
    assert remaining == []   # candidatos do loser removidos


def test_rededup_funde_par_proximo_com_nome_igual(session):
    # A ja existente (mais confianca), B recem-geocodado a <1km, nome quase igual
    a = _venue(session, "Mundo Pensante", lat=-23.550, lng=-46.630, confidence=40)
    b = _venue(session, "Mundo Pensante", lat=-23.551, lng=-46.631, confidence=15)
    out = rededup_geocoded(session, [b.id], reference=REF)
    session.flush()
    assert out["merged"] == 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    assert session.get(Venue, a.id) is not None   # A (maior confianca) sobrevive
    assert session.get(Venue, b.id) is None


def test_rededup_faixa_review_enfileira_sem_fundir(session):
    # nomes parecidos mas nao identicos: name_similarity=0.706 (faixa review
    # [0.70,0.85)); a 0.60km (>0.15km -> sem boost geo, score fica em 0.706).
    a = _venue(session, "Trackers", lat=-23.550, lng=-46.630, confidence=30)
    b = _venue(session, "Trackings", lat=-23.554, lng=-46.634, confidence=15)
    out = rededup_geocoded(session, [b.id], reference=REF)
    session.flush()
    assert out["review"] >= 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 2   # nao fundiu
    cand = session.scalars(select(DedupeCandidate).where(DedupeCandidate.kind == "venue")).all()
    assert len(cand) == 1


def test_rededup_par_longe_nao_funde(session):
    a = _venue(session, "Selva", lat=-23.55, lng=-46.63, confidence=30)
    b = _venue(session, "Selva", lat=-23.20, lng=-46.10, confidence=15)  # >1km
    out = rededup_geocoded(session, [b.id], reference=REF)
    session.flush()
    assert out["merged"] == 0
    assert session.scalar(select(func.count()).select_from(Venue)) == 2


def test_rededup_ignora_venue_ja_fundido(session):
    # A e B iguais e proximos; passar os dois ids nao deve estourar ao processar
    # o segundo (que ja foi apagado no merge do primeiro)
    a = _venue(session, "D-Edge", lat=-23.550, lng=-46.630, confidence=15)
    b = _venue(session, "D-Edge", lat=-23.551, lng=-46.631, confidence=40)
    out = rededup_geocoded(session, [a.id, b.id], reference=REF)
    session.flush()
    assert out["merged"] == 1
    assert session.scalar(select(func.count()).select_from(Venue)) == 1
    assert session.get(Venue, b.id) is not None   # B (maior confianca) sobrevive
