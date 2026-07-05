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


def test_venue_relevance():
    assert venue_relevance("Lab Club", "nightclub", False, False) == "relevant"
    assert venue_relevance("Buffet X", "nightclub", True, True) == "blocked"   # precedencia
    assert venue_relevance("Espaco Y", "events_venue", False, False) == "dormant"
    assert venue_relevance("Espaco Y", "events_venue", True, False) == "relevant"  # tem evento
    assert venue_relevance("Espaco Z", "events_venue", False, True) == "relevant"  # monitorado
    assert venue_relevance("Sem Cat", None, False, False) == "dormant"
