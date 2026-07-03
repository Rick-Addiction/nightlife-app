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
