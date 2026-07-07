from sqlalchemy import select

from nightlife.models import DedupeCandidate, Event, EventSource, Venue, VenueSource
from nightlife.repair_ra_dedup import repair


def test_repair_apaga_so_dados_ra(session):
    # venue OSM que absorveu evidencia RA falsa (sobrevive, perde a evidencia RA)
    osm = Venue(name="Mono Club", lat=-23.5, lng=-46.6)
    session.add(osm); session.flush()
    session.add_all([
        VenueSource(venue_id=osm.id, source_type="osm", source_url="https://osm.org/1"),
        VenueSource(venue_id=osm.id, source_type="ra", source_url="https://ra.co/clubs/1"),
    ])
    # venue RA-only orfao (some)
    ra_only = Venue(name="D-EDGE")
    session.add(ra_only); session.flush()
    session.add(VenueSource(venue_id=ra_only.id, source_type="ra", source_url="https://ra.co/clubs/2"))
    # evento RA-only (some)
    ev_ra = Event(name="Festa RA", status="scheduled")
    session.add(ev_ra); session.flush()
    session.add(EventSource(event_id=ev_ra.id, source_type="ra", source_url="https://ra.co/events/1"))
    # evento multi-fonte (sobrevive, perde a evidencia RA)
    ev_multi = Event(name="Festa Multi", status="scheduled")
    session.add(ev_multi); session.flush()
    session.add_all([
        EventSource(event_id=ev_multi.id, source_type="ra", source_url="https://ra.co/events/2"),
        EventSource(event_id=ev_multi.id, source_type="ticketing", source_url="https://sympla/9"),
    ])
    session.flush()

    repair(session)
    session.flush()

    assert session.get(Venue, osm.id) is not None                     # OSM sobrevive
    assert [s.source_type for s in session.scalars(
        select(VenueSource).where(VenueSource.venue_id == osm.id)).all()] == ["osm"]
    assert session.get(Venue, ra_only.id) is None                     # RA-only some
    assert session.get(Event, ev_ra.id) is None                       # evento RA-only some
    assert session.get(Event, ev_multi.id) is not None                # multi-fonte sobrevive
    assert [s.source_type for s in session.scalars(
        select(EventSource).where(EventSource.event_id == ev_multi.id)).all()] == ["ticketing"]
