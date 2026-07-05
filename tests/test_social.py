from nightlife.extraction.social import (
    canonical_handle, handles_from_text, handle_from_osm_tags, handle_from_jsonld,
)


def test_canonical_handle_normaliza_e_rejeita():
    assert canonical_handle("@MambaNegra") == "mambanegra"
    assert canonical_handle("instagram.com/gop_tun/") == "gop_tun"
    assert canonical_handle("https://www.instagram.com/mamba.negra?igshid=xyz") == "mamba.negra"
    assert canonical_handle("https://instagram.com/p/ABC123/") is None      # post, nao perfil
    assert canonical_handle("https://instagram.com/reel/XYZ/") is None      # reel
    assert canonical_handle("https://instagram.com/explore/") is None
    assert canonical_handle("https://mambanegra.com.br") is None            # site, nao IG
    assert canonical_handle("") is None
    assert canonical_handle(None) is None


def test_handles_from_text_pega_url_e_mencao():
    txt = "Line-up @deusa e @vhoor. Ingressos em https://www.instagram.com/mambanegra/ !"
    assert handles_from_text(txt) == {"deusa", "vhoor", "mambanegra"}
    assert handles_from_text("") == set()


def test_handle_from_osm_tags_prioriza_instagram():
    assert handle_from_osm_tags({"contact:instagram": "https://instagram.com/labclub"}) == "labclub"
    assert handle_from_osm_tags({"instagram": "@labclub"}) == "labclub"
    # so website, e website e uma URL de IG:
    assert handle_from_osm_tags({"website": "https://instagram.com/cargoclub"}) == "cargoclub"
    # website que NAO e IG -> None (nao inventa handle a partir do site proprio)
    assert handle_from_osm_tags({"website": "https://cargo.com.br"}) is None
    assert handle_from_osm_tags({}) is None


def test_nao_aceita_dominio_ou_email_como_handle():
    # website/contact:website com dominio proprio (mesmo sem esquema) NAO vira handle
    assert handle_from_osm_tags({"website": "cargo.com.br"}) is None
    assert handle_from_osm_tags({"contact:website": "www.cargo.com.br"}) is None
    # dominio de e-mail nao e handle (lookbehind na regex de @mencao)
    assert handles_from_text("fale com booking@gmail.com") == set()
    # mas o instagram real continua sendo pego
    assert handle_from_osm_tags({"website": "https://instagram.com/cargoclub"}) == "cargoclub"
    assert handles_from_text("segue la @mambanegra") == {"mambanegra"}


def test_handle_from_jsonld_varre_sameas():
    data = {"@type": "NightClub", "name": "Lab",
            "sameAs": ["https://facebook.com/lab", "https://www.instagram.com/lab.club/"]}
    assert handle_from_jsonld(data) == "lab.club"
    assert handle_from_jsonld({"sameAs": "https://instagram.com/soloig"}) == "soloig"
    assert handle_from_jsonld({"@graph": [{"sameAs": ["https://instagram.com/deep"]}]}) == "deep"
    assert handle_from_jsonld({"name": "sem redes"}) is None
