from datetime import datetime, timezone

from nightlife.ingestion.follow_source import run_follows
from nightlife.models import IgProfileState, Venue


def test_run_follows_marca_followed_at_e_para_no_checkpoint(session):
    for h in ("aura", "quebrado", "naoalcanca"):
        session.add(Venue(name=h, instagram=h, lat=-23.55, lng=-46.65, confidence=50))
    session.flush()
    seguidos = []

    class Checkpoint(Exception):
        pass

    def fake_follow(handle):
        if handle == "quebrado":
            raise Checkpoint("challenge_required")     # checkpoint -> auto-pausa
        seguidos.append(handle)

    n = run_follows(session, ["aura", "quebrado", "naoalcanca"],
                    follow=fake_follow, delay=lambda: None,
                    checkpoint_exc=Checkpoint)

    assert seguidos == ["aura"]                       # parou ANTES de naoalcanca
    assert n == 1
    st = session.query(IgProfileState).filter_by(handle="aura").one()
    assert st.followed_at is not None
    # quebrado NAO recebe followed_at (nao seguiu)
    assert session.query(IgProfileState).filter_by(handle="quebrado").one().followed_at is None
