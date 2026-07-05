from nightlife.ingestion.instagram_source import IgPost, parse_profile_posts, new_posts

# Formato GraphQL simplificado que o IG carrega numa pagina de perfil.
GRAPHQL = {
    "data": {"user": {"edge_owner_to_timeline_media": {"edges": [
        {"node": {"shortcode": "P3", "taken_at_timestamp": 1717800000,
                  "display_url": "https://cdn/p3.jpg",
                  "edge_media_to_caption": {"edges": [{"node": {"text": "Sabado! @deusa"}}]}}},
        {"node": {"shortcode": "P2", "taken_at_timestamp": 1717700000,
                  "display_url": "https://cdn/p2.jpg",
                  "edge_media_to_caption": {"edges": []}}},
        {"node": {"shortcode": "P1", "taken_at_timestamp": 1717600000,
                  "display_url": "https://cdn/p1.jpg",
                  "edge_media_to_caption": {"edges": [{"node": {"text": "flyer antigo"}}]}}},
    ]}}}
}


def test_parse_profile_posts():
    posts = parse_profile_posts(GRAPHQL)
    assert [p.shortcode for p in posts] == ["P3", "P2", "P1"]
    assert posts[0].image_url == "https://cdn/p3.jpg"
    assert posts[0].caption == "Sabado! @deusa"
    assert posts[1].caption is None
    assert posts[0].taken_at == 1717800000


MODERN = {  # shape moderno do IG (xdt/v1 feed), capturado no smoke real
    "data": {"xdt_api__v1__feed__user_timeline_graphql_connection": {"edges": [
        {"node": {"code": "CqbDvGMJdwO", "taken_at": 1680200512,
                  "caption": {"text": "Carioca Club show"},
                  "image_versions2": {"candidates": [
                      {"url": "https://cdn/big.jpg", "width": 1080},
                      {"url": "https://cdn/small.jpg", "width": 480}]}}},
        {"node": {"code": "Xyz12345678", "taken_at": 1680200000, "caption": None,
                  "image_versions2": {"candidates": [{"url": "https://cdn/2.jpg"}]}}},
    ]}}
}


def test_parse_profile_posts_shape_moderno_xdt():
    posts = parse_profile_posts(MODERN)
    assert [p.shortcode for p in posts] == ["CqbDvGMJdwO", "Xyz12345678"]
    assert posts[0].image_url == "https://cdn/big.jpg"   # candidates[0] = a maior
    assert posts[0].caption == "Carioca Club show"
    assert posts[1].caption is None                       # caption None no moderno
    assert posts[0].taken_at == 1680200512


def test_new_posts_para_no_cursor():
    posts = parse_profile_posts(GRAPHQL)
    # ja vimos P1 antes: so P3 e P2 sao novos
    assert [p.shortcode for p in new_posts(posts, last_shortcode="P1", cap=10)] == ["P3", "P2"]


def test_new_posts_respeita_cap():
    posts = parse_profile_posts(GRAPHQL)
    assert [p.shortcode for p in new_posts(posts, last_shortcode=None, cap=2)] == ["P3", "P2"]


def test_parse_profile_posts_vazio():
    assert parse_profile_posts({}) == []
    assert parse_profile_posts({"data": {"user": None}}) == []


def test_parse_rejeita_shortcode_malicioso():
    bad = {"data": {"user": {"edge_owner_to_timeline_media": {"edges": [
        {"node": {"shortcode": "../victim/pwned", "display_url": "u",
                  "edge_media_to_caption": {"edges": []}}},
        {"node": {"shortcode": "Bom_Shortcode-1", "display_url": "u2",
                  "edge_media_to_caption": {"edges": []}}},
    ]}}}}
    posts = parse_profile_posts(bad)
    assert [p.shortcode for p in posts] == ["Bom_Shortcode-1"]  # o malicioso e descartado


import json
from nightlife.ingestion.instagram_source import scrape_handle, ScrapeConfig


def test_scrape_handle_grava_imagem_e_sidecar(tmp_path):
    posts = [IgPost("P3", "https://cdn/p3.jpg", "Sabado @deusa", 1717800000),
             IgPost("P2", "https://cdn/p2.jpg", None, 1717700000)]

    def fetch_posts(handle):
        assert handle == "mambanegra"
        return posts

    downloaded = []

    def download(post, dest):  # simula baixar a imagem pro caminho dest
        dest.write_bytes(b"fakejpg")
        downloaded.append(post.shortcode)
        return dest

    cfg = ScrapeConfig(inbox=tmp_path, cap=10)
    result = scrape_handle("mambanegra", last_shortcode=None,
                           fetch_posts=fetch_posts, download=download, config=cfg)

    assert result.last_shortcode == "P3"      # mais recente vira o novo cursor
    assert downloaded == ["P3", "P2"]
    sidecar = json.loads((tmp_path / "P3.json").read_text(encoding="utf-8"))
    assert sidecar["handle"] == "mambanegra"
    assert sidecar["permalink"] == "https://www.instagram.com/p/P3/"
    assert sidecar["caption"] == "Sabado @deusa"
    assert (tmp_path / "P3.jpg").exists()


def test_scrape_handle_incremental_para_no_cursor(tmp_path):
    posts = [IgPost("P3", "u3", None, 3), IgPost("P2", "u2", None, 2), IgPost("P1", "u1", None, 1)]
    cfg = ScrapeConfig(inbox=tmp_path, cap=10)
    result = scrape_handle("h", last_shortcode="P2",
                           fetch_posts=lambda h: posts,
                           download=lambda p, d: d.write_bytes(b"x") or d, config=cfg)
    assert result.last_shortcode == "P3"          # so P3 e novo
    assert (tmp_path / "P3.jpg").exists()
    assert not (tmp_path / "P2.jpg").exists()


def test_scrape_handle_sem_posts_novos_mantem_cursor(tmp_path):
    cfg = ScrapeConfig(inbox=tmp_path, cap=10)
    result = scrape_handle("h", last_shortcode="P9",
                           fetch_posts=lambda h: [IgPost("P9", "u", None, 1)],
                           download=lambda p, d: d, config=cfg)
    assert result.last_shortcode == "P9"          # nada novo: cursor inalterado
    assert result.downloaded == 0


def test_scrape_handle_mantem_cursor_se_download_falha(tmp_path):
    # todos os downloads falham -> cursor NAO avanca (retry no proximo run)
    def boom(post, dest):
        raise OSError("rede caiu")

    cfg = ScrapeConfig(inbox=tmp_path, cap=10)
    result = scrape_handle("h", last_shortcode="P1",
                           fetch_posts=lambda h: [IgPost("P3", "u3", None, 3),
                                                  IgPost("P2", "u2", None, 2)],
                           download=boom, config=cfg)
    assert result.downloaded == 0
    assert result.last_shortcode == "P1"          # nao perdeu os posts
