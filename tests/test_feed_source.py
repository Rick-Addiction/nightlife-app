import json
from pathlib import Path

from nightlife.ingestion.feed_source import FeedItem, parse_feed_items

FIXTURE = json.loads((Path("tests/fixtures/feed_sample.json")).read_text(encoding="utf-8"))


def test_parse_feed_items_extrai_handle_shortcode_taken_at():
    items = parse_feed_items(FIXTURE)
    assert len(items) >= 2
    first = items[0]
    assert isinstance(first, FeedItem)
    assert first.handle          # @autor nao-vazio (o que o timeline de perfil NAO tem)
    assert first.shortcode
    assert first.taken_at is not None


def test_parse_feed_items_ignora_json_sem_feed():
    assert parse_feed_items({"data": {"outra_coisa": 1}}) == []


def test_parse_feed_items_pula_nao_post_e_media_incompleto():
    # ads/sugestoes tem node.media = None; media sem code/user tambem cai
    bad = {"data": {"xdt_api__v1__feed__timeline__connection": {"edges": [
        {"node": {"media": None, "ad": {"is_ad": True}}},           # nao-post
        {"node": {"media": {"code": "SC1"}}},                        # sem autor
        {"node": {"media": {"user": {"username": "selva.011"}}}},    # sem shortcode
    ]}}}
    assert parse_feed_items(bad) == []
