# tests/test_matching.py
from nightlife.domain.matching import (
    VenueRef, normalize_name, name_similarity, match_venue,
)


def test_normalize_strips_accents_and_stopwords():
    assert normalize_name("Bar do Zé") == normalize_name("bar do ze")
    assert "bar" not in normalize_name("Bar do Zé").split()


def test_similarity_high_for_same_name():
    assert name_similarity("Lab Club", "lab club") > 0.95


def test_similarity_low_for_different_names():
    assert name_similarity("Lab Club", "Trackers") < 0.4


def test_match_returns_best_above_threshold():
    existing = [
        VenueRef(1, "Lab Club"),
        VenueRef(2, "Trackers"),
    ]
    m = match_venue(VenueRef(None, "lab club"), existing)
    assert m is not None and m.venue.id == 1


def test_no_match_below_threshold():
    existing = [VenueRef(1, "Lab Club")]
    assert match_venue(VenueRef(None, "Audio SP"), existing) is None


def test_geo_proximity_boosts_score():
    # nome sozinho fica abaixo do threshold; a coordenada quase identica desempata
    existing = [VenueRef(1, "Cargo", lat=-23.561, lng=-46.656)]
    m = match_venue(VenueRef(None, "Cargo SP", lat=-23.5611, lng=-46.6561), existing)
    assert m is not None and m.venue.id == 1


def test_stopword_only_names_are_not_similar():
    # nomes so-de-stopword DIFERENTES nao podem ser tidos como identicos
    assert name_similarity("Bar", "Clube") < 0.5
    assert match_venue(VenueRef(None, "Clube"), [VenueRef(1, "Bar")]) is None


def test_stopword_only_name_matches_itself():
    # ...mas um venue chamado "A Casa" precisa casar consigo mesmo, senao
    # cada ingest cria uma duplicata nova
    assert name_similarity("A Casa", "A Casa") == 1.0
    m = match_venue(VenueRef(None, "A Casa"), [VenueRef(1, "A Casa")])
    assert m is not None and m.venue.id == 1


def test_classify_venue_match_bands():
    from nightlife.domain.matching import classify_venue_match
    # as faixas de merge/review/distinct valem COM geo (perto)
    assert classify_venue_match(0.90, distance_km=0.3) == "auto_merge"
    assert classify_venue_match(0.85, distance_km=0.3) == "auto_merge"
    assert classify_venue_match(0.78, distance_km=0.3) == "review"
    assert classify_venue_match(0.70, distance_km=0.3) == "review"
    assert classify_venue_match(0.60, distance_km=0.3) == "distinct"


def test_classify_venue_match_distance_gate():
    # duplicata FISICA nao pode estar a >1km de si mesma (calibrado c/ dados reais)
    from nightlife.domain.matching import classify_venue_match

    assert classify_venue_match(0.95, distance_km=5.0) == "distinct"
    assert classify_venue_match(0.75, distance_km=2.0) == "distinct"
    assert classify_venue_match(0.95, distance_km=0.3) == "auto_merge"
    assert classify_venue_match(0.75, distance_km=None) == "review"


def test_generic_venue_words_do_not_inflate_similarity():
    # pares reais que caiam em "review" so por compartilhar palavra generica
    assert name_similarity("Espaço Esplannada", "Espaço Estupendo") < 0.7
    assert name_similarity("Espaço TH Eventos", "Praça dos Eventos") < 0.7
    assert name_similarity("Teatro Mooca", "Teatro Bor") < 0.7


def test_classify_geoless_nunca_auto_merge():
    from nightlife.domain.matching import classify_venue_match
    # sem geo (distance_km=None) NAO da pra confirmar o lugar -> nunca auto_merge
    assert classify_venue_match(1.0, distance_km=None) == "review"
    assert classify_venue_match(0.90, distance_km=None) == "review"
    assert classify_venue_match(0.70, distance_km=None) == "review"
    assert classify_venue_match(0.60, distance_km=None) == "distinct"
