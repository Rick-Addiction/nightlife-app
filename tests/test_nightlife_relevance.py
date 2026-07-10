from nightlife.domain.nightlife_relevance import (
    is_buffet_name, is_platform_handle, venue_relevance,
)


def test_is_buffet_name():
    assert is_buffet_name("Buffet Planeta 1")
    assert is_buffet_name("Kairós Bistrô Buffet Infantil")
    assert is_buffet_name("FantastiKids Unidade III")          # 'kids'
    assert is_buffet_name("Célia Salão de Festas & Buffet")    # acento/case
    assert not is_buffet_name("Carioca Club")
    assert not is_buffet_name("Lab Club")
    assert not is_buffet_name(None)


def test_is_platform_handle():
    assert is_platform_handle("sympla")
    assert is_platform_handle("ifoodbrasil")
    assert is_platform_handle("Facebook")                      # case-insensitive
    assert not is_platform_handle("mambanegra")
    assert not is_platform_handle(None)


def test_venue_relevance_v2():
    # blocked tem precedencia sobre tudo
    assert venue_relevance("Buffet X", "nightclub", True, True) == "blocked"
    assert venue_relevance("Selva Club", "nightclub", True, True,
                           business_status="CLOSED_PERMANENTLY") == "blocked"
    # atividade vence sempre (qualquer categoria)
    assert venue_relevance("Espaco Y", "events_venue", True, False) == "relevant"
    assert venue_relevance("Espaco Z", "events_venue", False, True) == "relevant"
    # nightclub precisa estar VIVO: so-categoria nao basta mais (fantasmas do RA)
    assert venue_relevance("Lab Club", "nightclub", False, False) == "dormant"
    assert venue_relevance("Lab Club", "nightclub", False, False,
                           places_verified=True) == "relevant"
    assert venue_relevance("Lab Club", "nightclub", False, False,
                           source_count=2) == "relevant"
    assert venue_relevance("Lab Club", "nightclub", False, False,
                           has_contact=True) == "relevant"
    # nao-nightclub vivo mas sem evento continua dormant (bar verificado nao pina)
    assert venue_relevance("Bar Vivo", "bar", False, False,
                           places_verified=True) == "dormant"
    assert venue_relevance("Sem Cat", None, False, False) == "dormant"


def test_ig_stale_neutraliza_so_o_contato():
    # contato com IG parado ha 12+ meses nao prova vida
    assert venue_relevance("Lab Club", "nightclub", False, False,
                           has_contact=True, ig_stale=True) == "dormant"
    # mas Google OPERATIONAL (places_verified) vence IG quieto
    assert venue_relevance("Lab Club", "nightclub", False, False,
                           places_verified=True, ig_stale=True) == "relevant"
    # e atividade vence sempre
    assert venue_relevance("Lab Club", "nightclub", True, False,
                           ig_stale=True) == "relevant"
