from nightlife.ingestion.web_source import agenda_links, looks_empty, visible_text

HTML_HOME = """<html><body>
<a href="/agenda">Agenda</a>
<a href="https://selva.club/eventos">Próximos Eventos</a>
<a href="/sobre">Sobre nós</a>
<a href="https://outrodominio.com/agenda">externo</a>
<a href="/agenda">Agenda dup</a>
</body></html>"""


def test_agenda_links_casa_palavras_mesmo_dominio_dedup_cap():
    ls = agenda_links(HTML_HOME, base_url="https://selva.club/")
    assert "https://selva.club/agenda" in ls
    assert "https://selva.club/eventos" in ls
    assert all("outrodominio" not in u for u in ls)   # so mesmo dominio
    assert "https://selva.club/sobre" not in ls        # nao casa palavra
    assert len(ls) == len(set(ls))                     # dedup
    assert len(ls) <= 3


def test_looks_empty_sem_jsonld_e_texto_curto():
    assert looks_empty("<html><body><div></div></body></html>") is True
    assert looks_empty('<html><head><script type="application/ld+json">{}</script></head></html>') is False
    longo = "<html><body>" + ("Festa hoje na pista principal com muito open bar. " * 20) + "</body></html>"
    assert looks_empty(longo) is False   # texto renderavel longo


def test_visible_text_tira_tags_e_scripts():
    t = visible_text("<html><body><h1>AGENDA</h1><script>var x=1</script><p>SEX 25/07</p></body></html>")
    assert "AGENDA" in t and "SEX 25/07" in t
    assert "var x" not in t
