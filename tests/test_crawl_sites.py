from nightlife.crawl_sites import own_site_venues
from nightlife.models import Venue


def test_own_site_venues_exclui_ig_fb_linktree_e_sem_site(session):
    keep = Venue(name="Selva", website="https://selva.club", lat=-23.55, lng=-46.65, confidence=50)
    ig = Venue(name="IGsite", website="https://instagram.com/x", lat=-23.55, lng=-46.65, confidence=50)
    fb = Venue(name="FBsite", website="https://facebook.com/x", lat=-23.55, lng=-46.65, confidence=50)
    lt = Venue(name="LT", website="https://linktr.ee/x", lat=-23.55, lng=-46.65, confidence=50)
    none = Venue(name="Sem", website=None, lat=-23.55, lng=-46.65, confidence=50)
    session.add_all([keep, ig, fb, lt, none]); session.flush()
    handles = {v.name for v in own_site_venues(session)}
    assert handles == {"Selva"}
