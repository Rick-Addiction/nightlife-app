from datetime import date

from nightlife.extraction.post_actions import AddEvent, Ignore, PostInterpretation
from nightlife.ingestion.web_flow import crawl_venue, jsonld_to_actions
from nightlife.models import Event, Venue

REF = date(2026, 7, 18)

JSONLD_HTML = """<html><head><script type="application/ld+json">
{"@type":"Event","name":"Mamba Negra","startDate":"2026-07-25T23:00:00-03:00",
 "offers":{"url":"https://ticket.com/x"}}
</script></head><body>agenda</body></html>"""


def test_jsonld_to_actions_vira_add_event_com_iso():
    acts = jsonld_to_actions(JSONLD_HTML, source_url="https://selva.club/agenda")
    assert len(acts) == 1
    a = acts[0]
    assert a.name == "Mamba Negra"
    assert a.starts_at_iso.startswith("2026-07-25")
    assert a.ticket_url == "https://ticket.com/x"
    assert a.quotes.get("name") == "Mamba Negra"     # JSON-LD = quote pelo proprio nome


class FakeInterp:
    def __init__(self): self.calls = 0
    def interpret(self, doc, ctx):
        self.calls += 1
        return PostInterpretation(actions=[AddEvent(
            name="Do Codex", date_text="SAB 26/07",
            quotes={"name": "Do Codex", "date_text": "SAB 26/07"},
            confidence={"name": 0.9, "date_text": 0.9})])


def test_jsonld_to_actions_mantem_evento_sem_data():
    html = ('<html><head><script type="application/ld+json">'
            '{"@type":"Event","name":"Festa Sem Data"}</script></head></html>')
    acts = jsonld_to_actions(html, source_url="https://x.com")
    assert len(acts) == 1
    assert acts[0].name == "Festa Sem Data"
    assert acts[0].starts_at_iso is None


def test_crawl_venue_jsonld_nao_chama_codex(session):
    v = Venue(name="Selva Club", website="https://selva.club", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v); session.flush()
    fake = FakeInterp()
    stats = crawl_venue(session, v, fetcher=lambda url: JSONLD_HTML,
                        interpreter=fake, reference=REF)
    assert session.query(Event).filter_by(name="Mamba Negra").one().venue_id == v.id
    assert fake.calls == 0                     # JSON-LD resolveu, codex nao entrou
    assert v.web_last_hash is not None


def test_crawl_venue_sem_jsonld_chama_codex(session):
    v = Venue(name="X", website="https://x.com", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v); session.flush()
    fake = FakeInterp()
    html = "<html><body>" + ("programacao da semana muita festa " * 20) + "</body></html>"
    crawl_venue(session, v, fetcher=lambda url: html, interpreter=fake, reference=REF)
    assert fake.calls >= 1
    assert session.query(Event).filter_by(name="Do Codex").one().venue_id == v.id


def test_crawl_venue_cache_hit_pula(session):
    v = Venue(name="X", website="https://x.com", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v); session.flush()
    fake = FakeInterp()
    html = "<html><body>" + ("festa " * 60) + "</body></html>"
    crawl_venue(session, v, fetcher=lambda url: html, interpreter=fake, reference=REF)
    n1 = fake.calls
    stats2 = crawl_venue(session, v, fetcher=lambda url: html, interpreter=fake, reference=REF)
    assert stats2.get("skipped") is True
    assert fake.calls == n1                    # nao re-chamou


def test_crawl_venue_cache_hit_considera_subpaginas(session):
    # home estatica, mas a subpagina /agenda MUDA -> nao pode pular
    v = Venue(name="V", website="https://v.com", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v); session.flush()
    home = '<html><body><a href="/agenda">Agenda</a> casa noturna</body></html>'
    ag1 = "<html><body>" + ("SEX 25/07 Festa A " * 20) + "</body></html>"
    ag2 = "<html><body>" + ("SAB 26/07 Festa B " * 20) + "</body></html>"
    calls = {"n": 0}
    class FI:
        def interpret(self, doc, ctx):
            calls["n"] += 1
            return PostInterpretation(actions=[AddEvent(name=f"Festa{calls['n']}",
                date_text="SEX 25/07", quotes={"name": "x", "date_text": "x"},
                confidence={"name": 0.9, "date_text": 0.9})])
    def fetch_v1(url): return home if url == "https://v.com" else ag1
    def fetch_v2(url): return home if url == "https://v.com" else ag2
    crawl_venue(session, v, fetcher=fetch_v1, interpreter=FI(), reference=REF)
    n1 = calls["n"]
    stats = crawl_venue(session, v, fetcher=fetch_v2, interpreter=FI(), reference=REF)
    assert stats.get("skipped") is not True    # subpagina mudou -> re-extraiu
    assert calls["n"] > n1
