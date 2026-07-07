from datetime import date

from sqlalchemy import select, func

from nightlife.models import Venue, VenueSource, Event, DedupeCandidate
from nightlife.persistence.venue_merge import merge_venues

REF = date(2026, 6, 1)


def _venue(session, name, **kw):
    v = Venue(name=name, **kw)
    session.add(v)
    session.flush()
    return v


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
