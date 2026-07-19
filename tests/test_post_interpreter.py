# tests/test_post_interpreter.py
import json
from pathlib import Path

from nightlife.ingestion.post_interpreter import (
    Document, PostInterpreter, VenueContext, build_prompt,
)


CTX = VenueContext(venue_name="Selva Club", handle="selva.011", today_iso="2026-07-11",
                   known_events=[("WE LOVE POP", "2026-07-18"), ("NOITE X", None)])
DOC = Document(kind="ig_post", image_path=Path("x.jpg"), caption="mes de julho lotado",
               handle="selva.011", permalink="https://www.instagram.com/p/ABC/")


def test_build_prompt_injeta_contexto_e_legenda():
    p = build_prompt(DOC, CTX)
    for esperado in ("Selva Club", "@selva.011", "2026-07-11",
                     "WE LOVE POP (2026-07-18)", "NOITE X (data desconhecida)",
                     "mes de julho lotado", "add_event", "cancel_event", "ignore"):
        assert esperado in p


def test_interpret_parseia_acoes_do_runner():
    payload = {"actions": [
        {"type": "add_event", "name": "A", "date_text": "SEX 18/07",
         "quotes": {"name": "A", "date_text": "SEX 18/07"},
         "confidence": {"name": 0.9, "date_text": 0.9}},
        {"type": "add_event", "name": "B",
         "quotes": {"name": "B"}, "confidence": {"name": 0.8}},
    ]}
    fake = lambda image, prompt: f"blabla {json.dumps(payload)} tchau"
    it = PostInterpreter(runner=fake)
    out = it.interpret(DOC, CTX)
    assert [a.name for a in out.actions] == ["A", "B"]


def test_interpret_retry_e_none_em_lixo_persistente():
    calls = []
    def fake(image, prompt):
        calls.append(prompt)
        return "isso nao e json"
    it = PostInterpreter(runner=fake, retries=1)
    assert it.interpret(DOC, CTX) is None
    assert len(calls) == 2
    assert "invalida" in calls[1]     # re-prompt de correcao, padrao do CodexExtractor


CTX_WEB = VenueContext(venue_name="Selva Club", handle=None, today_iso="2026-07-18",
                       known_events=[("Mamba Negra", "2026-07-25")])


def _web_doc(text="AGENDA\nSEX 25/07 Mamba Negra"):
    return Document(kind="web_page", image_path=None, caption=None, handle=None,
                    permalink="https://selva.club/agenda", text=text, venue_id=7)


def test_build_prompt_web_usa_texto_da_pagina_e_contexto():
    p = build_prompt(_web_doc(), CTX_WEB)
    for esperado in ("Selva Club", "2026-07-18", "Mamba Negra (2026-07-25)",
                     "SEX 25/07 Mamba Negra", "add_event"):
        assert esperado in p
    assert "IMAGEM" not in p          # prompt web NAO fala de imagem


def test_interpret_web_usa_runner_de_texto():
    payload = {"actions": [{"type": "add_event", "name": "A", "date_text": "SEX 25/07",
               "quotes": {"name": "A", "date_text": "SEX 25/07"},
               "confidence": {"name": 0.9, "date_text": 0.9}}]}
    calls = []
    def fake_text_runner(prompt):
        calls.append(prompt)
        return f"blabla {json.dumps(payload)} fim"
    it = PostInterpreter(text_runner=fake_text_runner)
    out = it.interpret(_web_doc(), CTX_WEB)
    assert [a.name for a in out.actions] == ["A"]
    assert len(calls) == 1 and "IMAGEM" not in calls[0]
