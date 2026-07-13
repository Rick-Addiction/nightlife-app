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


def test_new_since_cursor_primeiro_poll_devolve_tudo():
    from nightlife.ingestion.feed_source import FeedItem, new_since_cursor
    items = [FeedItem("selva.011", "SC2", 200), FeedItem("blitzhaus", "BH1", 100)]
    novos = new_since_cursor(items, cursor_by_handle={})
    assert {i.shortcode for i in novos} == {"SC2", "BH1"}


def test_new_since_cursor_para_no_shortcode_ja_visto():
    from nightlife.ingestion.feed_source import FeedItem, new_since_cursor
    # feed vem do mais novo pro mais antigo; SC1 e o cursor de selva
    items = [FeedItem("selva.011", "SC2", 200), FeedItem("selva.011", "SC1", 100),
             FeedItem("selva.011", "SC0", 50)]
    novos = new_since_cursor(items, cursor_by_handle={"selva.011": "SC1"})
    assert [i.shortcode for i in novos] == ["SC2"]   # so o mais novo que SC1


def test_new_since_cursor_handle_sem_novidade():
    from nightlife.ingestion.feed_source import FeedItem, new_since_cursor
    items = [FeedItem("selva.011", "SC1", 100)]
    assert new_since_cursor(items, cursor_by_handle={"selva.011": "SC1"}) == []
