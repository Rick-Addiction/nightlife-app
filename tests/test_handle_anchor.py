# tests/test_handle_anchor.py
"""Ancoragem por handle: flyer postado pelo IG do proprio venue ancora nele
quando o nome escrito no flyer nao resolve. Organizer NUNCA ancora."""
from datetime import date

from nightlife.ingestion.base import RawEvent
from nightlife.ingestion.pipeline import run_ingestion
from nightlife.models import Event, Organizer, Venue


class _FakeSource:
    def __init__(self, events):
        self._events = events
    def venues(self):
        return []
    def event_pages(self):
        return []
    def events(self):
        return self._events


def _raw(name="Festa X", venue_name=None, source_handle=None):
    return RawEvent(name=name, source_type="vision_flyer",
                    venue_name=venue_name, source_handle=source_handle,
                    source_url="https://www.instagram.com/p/ABC123/")


def test_handle_de_venue_ancora_quando_nome_nao_resolve(session):
    v = Venue(name="Selva Club", instagram="selva.011", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    run_ingestion(session, _FakeSource([_raw(source_handle="selva.011")]),
                  reference=date(2026, 7, 10), label="flyers")
    ev = session.query(Event).filter_by(name="Festa X").one()
    assert ev.venue_id == v.id


def test_nome_que_resolve_tem_prioridade_sobre_handle(session):
    certo = Venue(name="Blitz Haus", lat=-23.552, lng=-46.652, confidence=50)
    dono = Venue(name="Selva Club", instagram="selva.011", lat=-23.55, lng=-46.65, confidence=50)
    session.add_all([certo, dono])
    session.flush()
    run_ingestion(session, _FakeSource([_raw(venue_name="Blitz Haus", source_handle="selva.011")]),
                  reference=date(2026, 7, 10), label="flyers")
    ev = session.query(Event).filter_by(name="Festa X").one()
    assert ev.venue_id == certo.id


def test_handle_de_organizer_nao_ancora(session):
    org = Organizer(name="Mamba Negra", instagram="mambanegra")
    session.add(org)
    session.flush()
    run_ingestion(session, _FakeSource([_raw(source_handle="mambanegra")]),
                  reference=date(2026, 7, 10), label="flyers")
    ev = session.query(Event).filter_by(name="Festa X").one()
    assert ev.venue_id is None


def test_handle_ambiguo_escolhe_maior_confianca(session):
    a = Venue(name="Dup A", instagram="dupclub", confidence=30)
    b = Venue(name="Dup B", instagram="dupclub", confidence=70)
    session.add_all([a, b])
    session.flush()
    run_ingestion(session, _FakeSource([_raw(source_handle="dupclub")]),
                  reference=date(2026, 7, 10), label="flyers")
    ev = session.query(Event).filter_by(name="Festa X").one()
    assert ev.venue_id == b.id
