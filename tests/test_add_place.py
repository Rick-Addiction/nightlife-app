from nightlife.add_place import ingest_pick, parse_matches


FAKE_RESPONSE = {"places": [
    {"id": "ChIJsupra123", "displayName": {"text": "Supra Club Augusta"},
     "formattedAddress": "R. Augusta, 765 - Consolação, São Paulo",
     "location": {"latitude": -23.5512, "longitude": -46.6531},
     "types": ["night_club", "bar"], "businessStatus": "OPERATIONAL"},
    {"id": "ChIJoutro456", "displayName": {"text": "Supra Bar"},
     "formattedAddress": "R. Alvaro Alvim, 76",
     "location": {"latitude": -23.556, "longitude": -46.641},
     "types": ["bar"], "businessStatus": "OPERATIONAL"},
]}


def test_parse_matches_extrai_campos_e_types():
    ms = parse_matches(FAKE_RESPONSE)
    assert ms[0].name == "Supra Club Augusta"
    assert ms[0].place_id == "ChIJsupra123"
    assert "night_club" in ms[0].types
    assert ms[0].lat == -23.5512


def test_ingest_pick_cria_venue_com_evidencia_places(session):
    from nightlife.models import Venue, VenueSource
    m = parse_matches(FAKE_RESPONSE)[0]
    v = ingest_pick(session, m, reference=__import__("datetime").date(2026, 7, 11))
    assert v.name == "Supra Club Augusta"
    assert v.lat == -23.5512
    assert v.category == "nightclub"          # night_club no types
    src = session.query(VenueSource).filter_by(venue_id=v.id).one()
    assert src.source_type == "google_places"
