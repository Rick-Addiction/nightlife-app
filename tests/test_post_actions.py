# tests/test_post_actions.py
from nightlife.extraction.post_actions import (
    AddEvent, CancelEvent, Ignore, PostInterpretation, UpdateEvent, sanitize_actions,
)


def _add(name="Festa X", quotes=None, confidence=None, **kw):
    return AddEvent(name=name, quotes=quotes or {}, confidence=confidence or {}, **kw)


def test_parse_uniao_discriminada():
    interp = PostInterpretation.model_validate({"actions": [
        {"type": "add_event", "name": "NOITE 1", "date_text": "SEX 18/07",
         "quotes": {"name": "NOITE 1", "date_text": "SEX 18/07"},
         "confidence": {"name": 0.9, "date_text": 0.9}},
        {"type": "cancel_event", "event_name": "WE LOVE POP", "quote": "CANCELADA", "confidence": 0.9},
        {"type": "ignore", "reason": "aniversario"},
    ]})
    assert [a.type for a in interp.actions] == ["add_event", "cancel_event", "ignore"]


def test_sanitize_add_sem_quote_do_nome_cai():
    interp = PostInterpretation(actions=[
        _add(quotes={}, confidence={"name": 0.9}),                       # sem quote: 0.45 < 0.5 -> cai
        _add(name="OK", quotes={"name": "OK"}, confidence={"name": 0.9}),
    ])
    out = sanitize_actions(interp)
    assert [a.name for a in out.actions] == ["OK"]


def test_sanitize_data_sem_quote_vira_none_mas_evento_fica():
    interp = PostInterpretation(actions=[
        _add(name="OK", date_text="18/07", quotes={"name": "OK"},
             confidence={"name": 0.9, "date_text": 0.9}),
    ])
    out = sanitize_actions(interp)
    assert out.actions[0].date_text is None      # data alucinada e pior que sem data
    assert out.actions[0].name == "OK"


def test_sanitize_cancel_update_exigem_quote_e_confianca():
    interp = PostInterpretation(actions=[
        CancelEvent(event_name="A", quote=None, confidence=0.9),          # sem quote -> cai
        CancelEvent(event_name="B", quote="CANCELADA", confidence=0.3),   # conf baixa -> cai
        CancelEvent(event_name="C", quote="ADIADA", confidence=0.8),      # fica
        UpdateEvent(event_name="D", changes={"date_text": "25/07"}, quote=None, confidence=0.9),
    ])
    out = sanitize_actions(interp)
    assert [a.event_name for a in out.actions] == ["C"]


def test_ignore_sempre_passa():
    interp = PostInterpretation(actions=[Ignore(reason="esporte", note="jogo do brasil")])
    assert len(sanitize_actions(interp).actions) == 1


def test_ignore_reason_desconhecido_vira_outro():
    # B7: reason fora do Literal (modelo alucinou uma categoria nova) nao
    # pode derrubar o post inteiro com ValidationError.
    assert Ignore.model_validate({"type": "ignore", "reason": "meme"}).reason == "outro"
    interp = PostInterpretation.model_validate({"actions": [
        {"type": "ignore", "reason": "meme"}]})
    assert interp.actions[0].reason == "outro"


def test_addevent_aceita_starts_at_iso():
    a = AddEvent(name="E", starts_at_iso="2026-07-25T23:00:00-03:00",
                 quotes={"name": "E"}, confidence={"name": 1.0})
    assert a.starts_at_iso.startswith("2026-07-25")
