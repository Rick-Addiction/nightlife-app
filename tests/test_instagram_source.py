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
