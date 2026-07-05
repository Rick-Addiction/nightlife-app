from nightlife.cleanup_relevance import cleanup
from nightlife.models import Event, Organizer, Venue


def test_cleanup_zera_handle_de_buffet_e_plataforma(session):
    vb = Venue(name="Buffet Alegria", instagram="buffetalegria")   # buffet -> zera
    vok = Venue(name="Club Bom", instagram="clubbom", category="nightclub")  # fica
    op = Organizer(name="Plat", instagram="sympla")                # platform -> zera
    ook = Organizer(name="Real", instagram="mambanegra")           # fica
    session.add_all([vb, vok, op, ook])
    session.flush()
    e = Event(name="Aniv", venue_id=vb.id, status="scheduled")     # evento em buffet
    session.add(e)
    session.flush()

    cleared_v, cleared_o, buffet_events = cleanup(session)
    session.flush()
    assert cleared_v == 1 and vb.instagram is None
    assert vok.instagram == "clubbom"                              # nao mexe no bom
    assert cleared_o == 1 and op.instagram is None
    assert ook.instagram == "mambanegra"
    assert buffet_events == 1                                       # reporta, NAO deleta
    assert session.get(Event, e.id) is not None                    # evento continua no banco
