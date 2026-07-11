from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from nightlife.extraction.post_actions import (
    AddEvent, CancelEvent, Ignore, PostInterpretation, UpdateEvent,
)
from nightlife.ingestion.post_interpreter import Document
from nightlife.models import Event, VerificationLog, Venue
from nightlife.persistence.action_executor import execute_actions
from pathlib import Path

_SP = ZoneInfo("America/Sao_Paulo")

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


def test_add_mesma_acao_duas_vezes_nao_duplica(session):
    # B1: _do_add sem venue_name capava o score do dedupe em 0.8 (nunca
    # auto_merge) -> a mesma acao executada 2x criava 2 linhas de Event.
    _venue(session)
    interp = PostInterpretation(actions=[_add("NOITE 1", "SEX 18/07")])
    execute_actions(session, _doc(), interp, reference=REF)
    execute_actions(session, _doc(), interp, reference=REF)
    assert session.query(Event).filter(Event.name == "NOITE 1").count() == 1


def test_add_ticket_url_generico_vira_none_e_real_passa(session):
    _venue(session)
    generico = AddEvent(name="FESTA LINK", ticket_url="https://linktr.ee/venue",
                        quotes={"name": "FESTA LINK", "ticket_url": "linktr.ee/venue"},
                        confidence={"name": 0.9, "ticket_url": 0.9})
    real = AddEvent(name="FESTA SYMPLA", ticket_url="https://www.sympla.com.br/evento/x",
                    quotes={"name": "FESTA SYMPLA", "ticket_url": "sympla"},
                    confidence={"name": 0.9, "ticket_url": 0.9})
    interp = PostInterpretation(actions=[generico, real])
    execute_actions(session, _doc(), interp, reference=REF)
    ev_generico = session.query(Event).filter(Event.name == "FESTA LINK").one()
    ev_real = session.query(Event).filter(Event.name == "FESTA SYMPLA").one()
    assert ev_generico.ticket_url is None
    assert ev_real.ticket_url == "https://www.sympla.com.br/evento/x"


def test_update_data_antiga_erra_mas_candidato_unico_move_data(session):
    # B3(ii): dated lookup nao bate (event_date_text errado/impreciso), mas o
    # venue so tem 1 candidato com esse nome -> fallback pro candidato unico.
    v = _venue(session)
    ev = Event(name="NOITE X", status="scheduled", confidence=50, venue_id=v.id,
               starts_at=datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc))  # SP: 18/07 22h
    session.add(ev)
    session.flush()
    interp = PostInterpretation(actions=[
        UpdateEvent(event_name="NOITE X", event_date_text="17/07",   # nao bate com nenhum dia
                    changes={"date_text": "SAB 25/07"}, quote="adiada para 25/07", confidence=0.9),
    ])
    stats = execute_actions(session, _doc(), interp, reference=REF)
    assert ev.starts_at.astimezone(_SP).day == 25
    assert stats["update"] == 1
    assert stats["update_candidate"] == 0


def test_update_2_candidatos_data_errada_vira_update_candidate_e_nao_muda_nada(session):
    # B3(iii): >=1 candidato por nome mas sem match forte -> update_candidate
    # auditavel, NUNCA silenciosamente vira add nem muta os candidatos.
    v = _venue(session)
    a = Event(name="FESTA", status="scheduled", confidence=50, venue_id=v.id,
              starts_at=datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc))
    b = Event(name="FESTA", status="scheduled", confidence=50, venue_id=v.id,
              starts_at=datetime(2026, 7, 25, 2, 0, tzinfo=timezone.utc))
    session.add_all([a, b])
    session.flush()
    interp = PostInterpretation(actions=[
        UpdateEvent(event_name="FESTA", event_date_text="01/08",     # nao bate com nenhuma
                    changes={"date_text": "10/08"}, quote="adiada", confidence=0.9),
    ])
    stats = execute_actions(session, _doc(), interp, reference=REF)
    assert a.starts_at == datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc)
    assert b.starts_at == datetime(2026, 7, 25, 2, 0, tzinfo=timezone.utc)
    assert stats["update_candidate"] == 1
    assert stats.get("add", 0) == 0
    assert session.query(Event).filter(Event.name == "FESTA").count() == 2
    assert session.query(VerificationLog).filter(
        VerificationLog.note.ilike("%update_candidate%")).count() == 1


def test_update_muda_nome_e_data_juntos_em_match_forte(session):
    # B3: match forte (nome antigo + data antiga = 1 so candidato no dia) ->
    # muda nome E data juntos.
    v = _venue(session)
    ev = Event(name="NOITE X", status="scheduled", confidence=50, venue_id=v.id,
               starts_at=datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc))  # SP: 18/07
    session.add(ev)
    session.flush()
    interp = PostInterpretation(actions=[
        UpdateEvent(event_name="NOITE X", event_date_text="18/07",
                    changes={"name": "NOITE X REBOOT", "date_text": "SAB 25/07"},
                    quote="mudou de nome e adiou", confidence=0.9),
    ])
    stats = execute_actions(session, _doc(), interp, reference=REF)
    assert ev.name == "NOITE X REBOOT"
    assert ev.starts_at.astimezone(_SP).day == 25
    assert stats["update"] == 1


def test_cancel_candidate_sem_venue_resolvido_nao_quebra(session):
    # B8: handle sem venue resolvido (vid None) -> cancel_candidate ainda loga
    # (entity_id=0, auditavel pela note) e nao explode.
    interp = PostInterpretation(actions=[
        CancelEvent(event_name="FESTA FANTASMA", quote="cancelamos", confidence=0.9)])
    stats = execute_actions(session, _doc(handle="handle.sem.venue"), interp, reference=REF)
    assert stats["cancel_candidate"] == 1
    log = session.query(VerificationLog).filter(
        VerificationLog.note.ilike("%cancel_candidate%")).one()
    assert log.entity_id == 0
