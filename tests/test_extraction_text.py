# tests/test_extraction_text.py
from datetime import date

from nightlife.extraction.html_patterns import parse_html_patterns
from nightlife.extraction.freetext import extract_freetext_deterministic

REF = date(2026, 6, 1)

FLYER_TEXT = """MAMBA NEGRA
SEX 13/06 a partir das 23h
Lab Club - São Paulo
ingressos: https://sympla.com.br/e/mamba
"""

HTML_MICRODATA = """
<div itemscope itemtype="https://schema.org/Event">
  <span itemprop="name">Carlos Capslock</span>
  <meta itemprop="startDate" content="2026-07-20T22:00:00-03:00">
</div>
"""


def test_freetext_extracts_name_date_and_ticket():
    ev = extract_freetext_deterministic(FLYER_TEXT, reference=REF, source_url="http://ig/x")
    assert ev.name == "MAMBA NEGRA"
    assert ev.starts_at is not None and ev.starts_at.day == 13 and ev.starts_at.hour == 23
    assert ev.ticket_url == "https://sympla.com.br/e/mamba"
    assert ev.source_url == "http://ig/x"
    assert ev.field_confidence.get("starts_at") == 0.5  # dia/mes sem ano => ambiguo


def test_freetext_without_date_has_no_starts_at():
    ev = extract_freetext_deterministic("apenas um nome de festa", reference=REF)
    assert ev.starts_at is None


def test_html_microdata_event():
    evs = parse_html_patterns(HTML_MICRODATA, source_url="http://site")
    assert len(evs) == 1
    assert evs[0].name == "Carlos Capslock"
    assert evs[0].starts_at_raw == "2026-07-20T22:00:00-03:00"
    assert evs[0].starts_at is not None and evs[0].starts_at.hour == 22


def test_freetext_strips_trailing_punctuation_from_ticket_url():
    text = "FESTA\n13/06\ningressos (https://sympla.com.br/e/x)."
    ev = extract_freetext_deterministic(text, reference=REF)
    assert ev.ticket_url == "https://sympla.com.br/e/x"


def test_freetext_preserves_balanced_parens_in_url():
    # ")" que fecha um "(" DENTRO da URL nao e pontuacao de prosa
    text = "FESTA\n13/06\nhttps://site.com.br/evento_(edicao-2)"
    ev = extract_freetext_deterministic(text, reference=REF)
    assert ev.ticket_url == "https://site.com.br/evento_(edicao-2)"


def test_freetext_ignores_generic_venue_links():
    # linktree/wa.me sao link de bio do venue, nao ticket — guardar isso em
    # ticket_url faria o dedupe fundir eventos distintos do mesmo club
    text = "FESTA A\n13/06 23h\nreservas: https://linktr.ee/clubx"
    ev = extract_freetext_deterministic(text, reference=REF)
    assert ev.ticket_url is None
