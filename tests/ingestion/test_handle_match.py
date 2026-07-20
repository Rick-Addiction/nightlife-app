import json
from pathlib import Path

from nightlife.ingestion.ig_search import SearchResult, parse_search_results
from nightlife.ingestion.handle_match import (
    ProfileSignals,
    MatchDecision,
    norm_url,
    shortlist,
    decide,
)

FIXTURE = json.loads(Path("tests/fixtures/ig_search_sample.json").read_text(encoding="utf-8"))


def test_shortlist_floor_filtra_mecanica_e_poe_oficina_club_primeiro():
    parsed = parse_search_results(FIXTURE)
    kept = shortlist("Oficina Club", parsed)
    usernames = [r.username for r in kept]
    assert "oficina_club" in usernames
    assert "oficinaclubcumbica" not in usernames
    assert usernames[0] == "oficina_club"


def test_norm_url_equivalencia_e_diferenca():
    a = norm_url("https://www.OficinaClub.com.br/")
    b = norm_url("http://oficinaclub.com.br")
    assert a == b == "oficinaclub.com.br"

    c = norm_url("https://www.facebook.com/oficinaclub")
    assert c != a


def test_decide_attach_via_bio_link_igual_ao_site():
    parsed = parse_search_results(FIXTURE)
    best = next(r for r in parsed if r.username == "oficina_club")
    signals = ProfileSignals(
        handle="oficina_club",
        bio_link="https://oficinaclub.com.br/",
        category=None,
        bio_text=None,
        is_verified=False,
        follower_count=None,
    )
    decision = decide(
        venue_name="Oficina Club",
        venue_website="http://www.oficinaclub.com.br",
        venue_neighborhood=None,
        best=best,
        signals=signals,
    )
    assert decision.action == "attach"
    assert "bio_link" in decision.reason
    assert decision.handle == "oficina_club"


def test_decide_attach_via_verificado_e_nome_forte():
    best = SearchResult(
        username="oficina_club",
        full_name="Oficina Club",
        is_verified=True,
        is_private=False,
    )
    signals = ProfileSignals(
        handle="oficina_club",
        bio_link=None,
        category=None,
        bio_text=None,
        is_verified=True,
        follower_count=1000,
    )
    decision = decide(
        venue_name="Oficina Club",
        venue_website=None,
        venue_neighborhood=None,
        best=best,
        signals=signals,
    )
    assert decision.action == "attach"
    assert "verificado" in decision.reason


def test_decide_attach_via_categoria_nightlife_e_bairro():
    best = SearchResult(
        username="oficina_club",
        full_name="Oficina Club",
        is_verified=False,
        is_private=False,
    )
    signals = ProfileSignals(
        handle="oficina_club",
        bio_link=None,
        category="Nightclub",
        bio_text="A melhor balada de Barra Funda, Sao Paulo",
        is_verified=False,
        follower_count=None,
    )
    decision = decide(
        venue_name="Oficina Club",
        venue_website=None,
        venue_neighborhood="Barra Funda",
        best=best,
        signals=signals,
    )
    assert decision.action == "attach"
    assert "categoria" in decision.reason


def test_decide_review_quando_so_sinais_fracos():
    best = SearchResult(
        username="oficina.club_",
        full_name="OficinaClub",
        is_verified=False,
        is_private=False,
    )
    signals = ProfileSignals(
        handle="oficina.club_",
        bio_link="https://linktr.ee/algumacoisa",
        category=None,
        bio_text=None,
        is_verified=False,
        follower_count=None,
    )
    decision = decide(
        venue_name="Oficina Club",
        venue_website="http://www.oficinaclub.com.br",
        venue_neighborhood=None,
        best=best,
        signals=signals,
    )
    assert decision.action == "review"


def test_decide_reject_handle_de_plataforma():
    best = SearchResult(
        username="sympla",
        full_name="Sympla",
        is_verified=True,
        is_private=False,
    )
    signals = ProfileSignals(
        handle="sympla",
        bio_link=None,
        category=None,
        bio_text=None,
        is_verified=True,
        follower_count=None,
    )
    decision = decide(
        venue_name="Oficina Club",
        venue_website=None,
        venue_neighborhood=None,
        best=best,
        signals=signals,
    )
    assert decision.action == "reject"


def test_decide_reject_handle_invalido():
    best = SearchResult(
        username="p",
        full_name="",
        is_verified=False,
        is_private=False,
    )
    signals = ProfileSignals(
        handle="p",
        bio_link=None,
        category=None,
        bio_text=None,
        is_verified=False,
        follower_count=None,
    )
    decision = decide(
        venue_name="Oficina Club",
        venue_website=None,
        venue_neighborhood=None,
        best=best,
        signals=signals,
    )
    assert decision.action == "reject"
