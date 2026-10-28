# tests/test_shotgun_source.py
from datetime import date

from nightlife.ingestion.shotgun_source import (
    ShotgunSource, infer_year, is_area_name, parse_cards,
)

REF = date(2026, 10, 28)

# Estrutura dos cards observada em 2026-10-28 (nome, venue, "DD de mes. | HH:MM",
# preco/status, tags). Datas em outubro/novembro relativas a REF.
HTML = """
<main>
<a href="/pt-br/events/mamba-negra-presidenta"><div><h3>Mamba Negra ☆ Presidenta ☆</h3>
 <p>Presidenta Bar</p><div><span>31 de out.</span><span>|</span><span>22:00</span></div>
 <span>R$&nbsp;100,00</span><ul><li>Techno</li><li>House</li><li>+3</li></ul></div></a>
<a href="/pt-br/events/hlwn-socialclub"><div><h3>Hlwn Social Club</h3>
 <p>Barra Funda</p><div><span>31 de out.</span><span>|</span><span>22:00</span></div>
 <span>R$ 105,00</span></div></a>
<a href="/pt-br/events/technoguetto"><div><h3>Technoguetto</h3>
 <p>Parque Regina</p><div><span>31 de out.</span><span>|</span><span>21:00</span></div>
 <span>Gratuito</span><ul><li>Techno</li></ul></div></a>
<a href="/pt-br/events/gagaween"><div><h3>Gagaween 2026</h3>
 <p>ZIG Studio</p><div><span>31 de out.</span><span>|</span><span>23:30</span></div>
 <span>Lista de espera</span><ul><li>Pop</li></ul></div></a>
<a href="/pt-br/events/reveillon-x"><div><h3>Reveillon X</h3>
 <p>Casa Y</p><div><span>2 de jan.</span><span>|</span><span>23:00</span></div>
 <span>R$ 50,00</span></div></a>
<a href="/pt-br/events/passado"><div><h3>Festa Passada</h3>
 <p>Bar Z</p><div><span>27 de out.</span><span>|</span><span>22:00</span></div></div></a>
<a href="/pt-br/events/sem-data"><div><h3>Sem Data</h3><p>Bar W</p></div></a>
<a href="/pt-br/events/mamba-negra-presidenta"><div><h3>Mamba Negra ☆ Presidenta ☆ (dup)</h3>
 <p>Presidenta Bar</p><div><span>31 de out.</span><span>|</span><span>22:00</span></div></div></a>
<a href="/pt-br/cities/rio-de-janeiro">Rio</a>
</main>
"""


def test_parse_cards_maps_and_filters():
    evs = parse_cards(HTML, reference=REF)
    names = [e.name for e in evs]
    # passado, sem data e href duplicado ficam de fora; "27 de out." (ontem) < REF => passado.
    # (a listagem so tem futuros: dia bem anterior no mesmo mes vira o ANO QUE VEM)
    assert names == ["Mamba Negra ☆ Presidenta ☆", "Hlwn Social Club", "Technoguetto",
                     "Gagaween 2026", "Reveillon X"]
    mamba = evs[0]
    assert mamba.source_type == "shotgun"
    assert mamba.starts_at is not None
    assert mamba.starts_at.isoformat() == "2026-10-31T22:00:00-03:00"
    assert mamba.venue is not None and mamba.venue.name == "Presidenta Bar"
    assert mamba.venue.category == "nightclub" and mamba.venue.source_type == "shotgun"
    assert mamba.genre == "Techno"
    assert mamba.ticket_url == "https://shotgun.live/pt-br/events/mamba-negra-presidenta"
    assert mamba.source_url == mamba.ticket_url
    assert '"price": "R$ 100,00"' in mamba.raw_payload
    assert '"tags": ["Techno", "House"]' in mamba.raw_payload


def test_area_name_is_not_a_venue():
    evs = {e.name: e for e in parse_cards(HTML, reference=REF)}
    assert evs["Hlwn Social Club"].venue is None          # "Barra Funda" = bairro
    assert evs["Technoguetto"].venue is None              # "Parque Regina" = bairro
    assert evs["Technoguetto"].genre == "Techno"           # tags depois de "Gratuito"
    assert evs["Gagaween 2026"].venue is not None          # ZIG Studio = venue
    assert '"status": "Lista de espera"' in evs["Gagaween 2026"].raw_payload
    assert is_area_name("São Paulo, Brasil 🇧🇷")
    assert is_area_name("Consolação, Brasil 🇧🇷")
    assert is_area_name("Centro Histórico De São Paulo, Brasil 🇧🇷")
    assert not is_area_name("Bar do Netão")
    assert not is_area_name("Estúdio Lâmina")


def test_infer_year_rolls_over():
    assert infer_year(31, 10, reference=REF) == 2026
    assert infer_year(2, 1, reference=REF) == 2027
    assert infer_year(28, 10, reference=REF) == 2026
    evs = {e.name: e for e in parse_cards(HTML, reference=REF)}
    assert evs["Reveillon X"].starts_at.year == 2027


def test_source_other_methods_and_paging_urls():
    src = ShotgunSource()
    assert src.venues() == [] and src.event_pages() == []
    assert src.page_url(0) == "https://shotgun.live/pt-br/cities/sao-paulo"
    assert src.page_url(3) == "https://shotgun.live/pt-br/cities/sao-paulo?page=3"


class _FakeResp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_events_pages_until_empty_and_dedupes(monkeypatch):
    import nightlife.ingestion.shotgun_source as mod

    pages = {0: HTML, 1: HTML, 2: "<main></main>"}  # pagina 1 repete => nada novo => para
    urls: list[str] = []

    def fake_get(url, *, headers, timeout, follow_redirects):
        urls.append(url)
        page = int(url.split("page=")[1]) if "page=" in url else 0
        return _FakeResp(pages[page])

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    evs = ShotgunSource(reference=REF).events()
    assert len(evs) == 5
    assert urls == ["https://shotgun.live/pt-br/cities/sao-paulo",
                    "https://shotgun.live/pt-br/cities/sao-paulo?page=1"]
