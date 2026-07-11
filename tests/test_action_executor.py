from datetime import date, datetime, timezone

from nightlife.extraction.post_actions import (
    AddEvent, CancelEvent, Ignore, PostInterpretation, UpdateEvent,
)
from nightlife.ingestion.post_interpreter import Document
from nightlife.models import Event, VerificationLog, Venue
from nightlife.persistence.action_executor import execute_actions
from pathlib import Path

REF = date(2026, 7, 11)


def _doc(handle="selva.011"):
    return Document(kind="ig_post", image_path=Path("x.jpg"), caption=None,
                    handle=handle, permalink="https://www.instagram.com/p/ABC/")


def _venue(session, name="Selva Club", handle="selva.011"):
    v = Venue(name=name, instagram=handle, lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    return v


def _add(name, date_text=None):
    q = {"name": name}
    c = {"name": 0.9}
    if date_text:
        q["date_text"] = date_text
        c["date_text"] = 0.9
    return AddEvent(name=name, date_text=date_text, quotes=q, confidence=c)


def test_add_multi_evento_ancora_por_handle_e_permite_sem_data(session):
    v = _venue(session)
    interp = PostInterpretation(actions=[_add("NOITE 1", "SEX 18/07"), _add("TEASER")])
    stats = execute_actions(session, _doc(), interp, reference=REF)
    evs = session.query(Event).filter(Event.venue_id == v.id).all()
    assert {e.name for e in evs} == {"NOITE 1", "TEASER"}
    com_data = next(e for e in evs if e.name == "NOITE 1")
    sem_data = next(e for e in evs if e.name == "TEASER")
    assert com_data.starts_at is not None
    assert sem_data.starts_at is None            # DATA A CONFIRMAR
    assert stats["add"] == 2


def test_cancel_com_prova_forte_cancela_e_loga(session):
    v = _venue(session)
    ev = Event(name="WE LOVE POP", status="scheduled", confidence=50, venue_id=v.id,
               starts_at=datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc))  # SP: 18/07 22h
    session.add(ev)
    session.flush()
    interp = PostInterpretation(actions=[
        CancelEvent(event_name="we love pop", event_date_text="18/07",
                    quote="CANCELADA", confidence=0.9)])
    stats = execute_actions(session, _doc(), interp, reference=REF)
    assert ev.status == "cancelled"
    assert stats["cancel"] == 1
    assert session.query(VerificationLog).filter(
        VerificationLog.note.ilike("%cancelado%")).count() == 1


def test_cancel_sem_match_forte_vira_candidato_e_nao_toca(session):
    v = _venue(session)
    a = Event(name="FESTA", status="scheduled", confidence=50, venue_id=v.id,
              starts_at=datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc))
    b = Event(name="FESTA", status="scheduled", confidence=50, venue_id=v.id,
              starts_at=datetime(2026, 7, 25, 2, 0, tzinfo=timezone.utc))
    session.add_all([a, b])
    session.flush()
    interp = PostInterpretation(actions=[
        CancelEvent(event_name="FESTA", quote="cancelamos", confidence=0.8)])  # SEM data: 2 candidatos
    stats = execute_actions(session, _doc(), interp, reference=REF)
    assert a.status == "scheduled" and b.status == "scheduled"
    assert stats["cancel_candidate"] == 1
    assert session.query(VerificationLog).filter(
        VerificationLog.note.ilike("%cancel_candidate%")).count() == 1


def test_update_com_match_muda_data_e_sem_match_vira_add(session):
    v = _venue(session)
    ev = Event(name="NOITE X", status="scheduled", confidence=50, venue_id=v.id,
               starts_at=datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc))  # SP: 18/07 22h
    session.add(ev)
    session.flush()
    interp = PostInterpretation(actions=[
        UpdateEvent(event_name="NOITE X", event_date_text="18/07",
                    changes={"date_text": "SAB 25/07"}, quote="adiada para 25/07", confidence=0.9),
        UpdateEvent(event_name="INEDITA", changes={"date_text": "26/07"},
                    quote="nova data 26/07", confidence=0.9),
    ])
    stats = execute_actions(session, _doc(), interp, reference=REF)
    assert ev.starts_at.astimezone(__import__('zoneinfo').ZoneInfo('America/Sao_Paulo')).day == 25
    assert stats["update"] == 1
    assert session.query(Event).filter(Event.name == "INEDITA").count() == 1  # virou add
    assert stats["add"] == 1


def test_ignore_so_conta(session):
    _venue(session)
    interp = PostInterpretation(actions=[Ignore(reason="esporte")])
    stats = execute_actions(session, _doc(), interp, reference=REF)
    assert stats["ignore"] == {"esporte": 1}
    assert session.query(Event).count() == 0
