from nightlife.ingestion.handle_discovery import handle_from_html


def test_handle_from_html_prefere_jsonld():
    html = """<html><head>
      <script type="application/ld+json">
      {"@type":"NightClub","name":"Lab","sameAs":["https://instagram.com/lab.oficial"]}
      </script></head>
      <body><a href="https://instagram.com/outro">rodape</a></body></html>"""
    assert handle_from_html(html) == "lab.oficial"


def test_handle_from_html_cai_pra_texto_quando_sem_jsonld():
    html = '<html><body><a href="https://www.instagram.com/soanchor/">IG</a></body></html>'
    assert handle_from_html(html) == "soanchor"


def test_handle_from_html_none_quando_nao_ha_ig():
    assert handle_from_html("<html><body>sem redes</body></html>") is None
    assert handle_from_html("") is None


def test_handle_from_html_ignora_ruido_de_at_rules_e_jsonld():
    # @context (JSON-LD) e @font-face/@media (CSS) NAO podem virar handle
    html = """<html><head>
      <style>@font-face { font-family: X; } @media (max-width: 5px) {}</style>
      <script type="application/ld+json">{"@context":"https://schema.org","name":"Bar"}</script>
      </head><body>segue @font e @context la</body></html>"""
    assert handle_from_html(html) is None
    # mas se houver uma URL de IG de verdade, pega
    assert handle_from_html(html.replace("</body>", '<a href="https://instagram.com/barreal">ig</a></body>')) == "barreal"


from nightlife.ingestion.handle_discovery import discover_venue_handles
from nightlife.ingestion.osm_source import parse_overpass_tags
from nightlife.models import Venue, VenueSource

OSM_URL = "https://www.openstreetmap.org/node/1"


def _osm_venue(session, name):
    v = Venue(name=name)
    session.add(v)
    session.flush()
    session.add(VenueSource(venue_id=v.id, source_type="osm", source_url=OSM_URL))
    session.flush()
    return v


def test_parse_overpass_tags_mapeia_por_url():
    data = {"elements": [
        {"type": "node", "id": 1, "tags": {"name": "Lab", "contact:instagram": "@lab"}},
        {"type": "way", "id": 2, "tags": {"name": "Cargo"}},
    ]}
    out = parse_overpass_tags(data)
    assert out["https://www.openstreetmap.org/node/1"]["contact:instagram"] == "@lab"
    assert out["https://www.openstreetmap.org/way/2"] == {"name": "Cargo"}


def test_discover_venue_via_osm_tag(session):
    v = _osm_venue(session, "Lab Club")
    tags = {OSM_URL: {"contact:instagram": "@labclub"}}

    def fetch(url):
        raise AssertionError("fetch nao deveria ser chamado")

    n = discover_venue_handles(session, osm_tags_by_url=tags, fetch=fetch)
    session.flush()
    assert n == 1
    assert v.instagram == "labclub"


def test_discover_venue_via_site_fetch(session):
    v = _osm_venue(session, "Cargo")
    tags = {OSM_URL: {"website": "https://cargo.com.br"}}

    def fetch(url):
        assert url == "https://cargo.com.br"
        return '<html><body><a href="https://instagram.com/cargoclub">ig</a></body></html>'

    n = discover_venue_handles(session, osm_tags_by_url=tags, fetch=fetch)
    session.flush()
    assert n == 1
    assert v.instagram == "cargoclub"
    assert v.website == "https://cargo.com.br"


def test_discover_venue_idempotente(session):
    v = Venue(name="Ja Tem", instagram="jatem")
    session.add(v)
    session.flush()
    n = discover_venue_handles(session, osm_tags_by_url={}, fetch=lambda u: None)
    assert n == 0
    assert v.instagram == "jatem"  # nao sobrescreve


from nightlife.ingestion.handle_discovery import discover_organizer_handles
from nightlife.models import Event, EventSource, Organizer


def test_discover_organizer_via_sympla_page(session):
    org = Organizer(name="Mamba Negra")
    session.add(org)
    session.flush()
    ev = Event(name="Mamba", organizer_id=org.id)
    session.add(ev)
    session.flush()
    session.add(EventSource(event_id=ev.id, source_type="ticketing",
                            source_url="https://sympla.com.br/evento/mamba/123"))
    session.flush()

    def fetch(url):
        assert "sympla" in url
        return '<html><body><a href="https://instagram.com/mambanegra">ig</a></body></html>'

    n = discover_organizer_handles(session, fetch=fetch)
    session.flush()
    assert n == 1
    assert org.instagram == "mambanegra"


def test_discover_organizer_idempotente(session):
    org = Organizer(name="Ja", instagram="ja")
    session.add(org)
    session.flush()
    n = discover_organizer_handles(session, fetch=lambda u: None)
    assert n == 0


def test_discover_venue_pula_buffet(session):
    v = _osm_venue(session, "Buffet Planeta 1")
    tags = {OSM_URL: {"contact:instagram": "@buffetplaneta"}}
    n = discover_venue_handles(session, osm_tags_by_url=tags, fetch=lambda u: None)
    session.flush()
    assert n == 0
    assert v.instagram is None            # buffet nem e considerado


def test_discover_venue_descarta_platform_handle(session):
    v = _osm_venue(session, "Casa X")
    tags = {OSM_URL: {"contact:instagram": "@sympla"}}
    n = discover_venue_handles(session, osm_tags_by_url=tags, fetch=lambda u: None)
    session.flush()
    assert n == 0
    assert v.instagram is None            # sympla e handle de plataforma


def test_discover_organizer_descarta_platform_handle(session):
    org = Organizer(name="Org Y")
    session.add(org)
    session.flush()
    ev = Event(name="E", organizer_id=org.id)
    session.add(ev)
    session.flush()
    session.add(EventSource(event_id=ev.id, source_type="ticketing",
                            source_url="https://sympla.com.br/evento/y/9"))
    session.flush()
    n = discover_organizer_handles(
        session,
        fetch=lambda u: '<a href="https://instagram.com/sympla">x</a>')
    session.flush()
    assert n == 0
    assert org.instagram is None


def test_discover_venue_via_venue_website(session):
    # site oficial JA no banco (ex.: websiteUri do Places) e fonte de handle
    v = Venue(name="Selva Club", website="https://selva.club/")
    session.add(v)
    session.flush()
    html = '<a href="https://www.instagram.com/selva.011/">IG</a>'
    fetched = []
    def fetch(url):
        fetched.append(url)
        return html
    n = discover_venue_handles(session, osm_tags_by_url={}, fetch=fetch)
    assert n == 1 and v.instagram == "selva.011"
    assert fetched == ["https://selva.club/"]


def test_discover_venue_website_que_ja_e_perfil_de_ig(session):
    # muitos clubes usam o IG como site: websiteUri = instagram.com/handle
    # -> handle de graca, SEM fetch
    v = Venue(name="Bar do X", website="https://www.instagram.com/bardox/")
    session.add(v)
    session.flush()
    def fetch(url):
        raise AssertionError("nao deveria fazer fetch")
    n = discover_venue_handles(session, osm_tags_by_url={}, fetch=fetch)
    assert n == 1 and v.instagram == "bardox"


def test_discover_venue_tag_osm_vence_o_site_do_banco(session):
    # com contact:instagram na tag OSM, nem olha o venue.website
    from nightlife.persistence.evidence import record_venue_evidence
    from nightlife.persistence.inputs import SourceInfo
    v = Venue(name="Club Y", website="https://site-que-nao-deve-ser-buscado.com")
    session.add(v)
    session.flush()
    record_venue_evidence(session, v.id, SourceInfo(
        source_type="osm", source_url="https://osm.org/node/9"), contribution=20)
    def fetch(url):
        raise AssertionError("nao deveria fazer fetch")
    n = discover_venue_handles(
        session, osm_tags_by_url={"https://osm.org/node/9": {"contact:instagram": "clubey"}},
        fetch=fetch)
    assert n == 1 and v.instagram == "clubey"
