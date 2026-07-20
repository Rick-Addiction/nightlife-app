import json
from pathlib import Path

from nightlife.ingestion.ig_search import SearchResult, parse_search_results

FIXTURE = json.loads(Path("tests/fixtures/ig_search_sample.json").read_text(encoding="utf-8"))


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
