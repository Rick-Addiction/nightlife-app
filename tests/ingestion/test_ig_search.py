import json
from pathlib import Path

from nightlife.ingestion.handle_match import ProfileSignals
from nightlife.ingestion.ig_search import SearchResult, parse_profile_signals, parse_search_results

FIXTURE = json.loads(Path("tests/fixtures/ig_search_sample.json").read_text(encoding="utf-8"))
PROFILE_FIXTURE = json.loads(Path("tests/fixtures/ig_profile_sample.json").read_text(encoding="utf-8"))


def test_parse_search_results_extrai_usernames_na_ordem():
    results = parse_search_results(FIXTURE)
    assert len(results) == 5
    assert [r.username for r in results] == [
        "oficina_club",
        "oficina.club_",
        "oficina.club._",
        "oficinaclubcumbica",
        "ofic.inaclub",
    ]


def test_parse_search_results_primeiro_resultado_tem_full_name_e_flags():
    results = parse_search_results(FIXTURE)
    first = results[0]
    assert isinstance(first, SearchResult)
    assert first.full_name == "Oficina Club"
    assert first.is_verified is False
    assert isinstance(first.is_private, bool)


def test_parse_search_results_payload_vazio_retorna_lista_vazia():
    assert parse_search_results({}) == []


def test_parse_search_results_users_none_retorna_lista_vazia():
    assert parse_search_results({"users": None}) == []


def test_parse_search_results_pula_entrada_sem_user():
    payload = {"users": [
        {"position": 0},
        {"position": 1, "user": {"username": "valido", "full_name": "Valido",
                                  "is_verified": True, "is_private": False}},
    ]}
    results = parse_search_results(payload)
    assert [r.username for r in results] == ["valido"]


def test_parse_profile_signals_extrai_campos_da_fixture():
    signals = parse_profile_signals("oficina_club", PROFILE_FIXTURE)
    assert isinstance(signals, ProfileSignals)
    assert signals.handle == "oficina_club"
    assert signals.bio_link == "https://cheers.com.br/pagina/oficina-club~14785"
    assert signals.category is None
    assert "Baixo Augusta" in signals.bio_text
    assert signals.is_verified is False
    assert signals.follower_count == 8677


def test_parse_profile_signals_payload_vazio_nao_estoura():
    signals = parse_profile_signals("x", {})
    assert isinstance(signals, ProfileSignals)
    assert signals.handle == "x"
    assert signals.bio_link is None
    assert signals.category is None
    assert signals.bio_text is None
    assert signals.is_verified is False
    assert signals.follower_count is None


def test_parse_profile_signals_bio_links_vazio_cai_pro_external_url():
    payload = {
        "data": {
            "user": {
                "bio_links": [],
                "external_url": "https://example.com/fallback",
                "category_name": None,
                "business_category_name": None,
                "biography": "bio",
                "is_verified": True,
                "edge_followed_by": {"count": 42},
            }
        }
    }
    signals = parse_profile_signals("y", payload)
    assert signals.bio_link == "https://example.com/fallback"
    assert signals.is_verified is True
    assert signals.follower_count == 42
