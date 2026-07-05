from nightlife.ingestion.handle_discovery import handle_from_html


def test_handle_from_html_prefere_jsonld():
    html = """<html><head>
      <script type="application/ld+json">
      {"@type":"NightClub","name":"Lab","sameAs":["https://instagram.com/lab.oficial"]}
      </script></head>
      <body><a href="https://instagram.com/outro">rodape</a></body></html>"""
    assert handle_from_html(html) == "lab.oficial"


def test_handle_from_html_cai_pra_texto_quando_sem_jsonld():
    html = '<html><body><a href="https://www.instagram.com/soanchor/">IG</a></body></html>'
    assert handle_from_html(html) == "soanchor"


def test_handle_from_html_none_quando_nao_ha_ig():
    assert handle_from_html("<html><body>sem redes</body></html>") is None
    assert handle_from_html("") is None
