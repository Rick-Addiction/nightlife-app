from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from nightlife.models import AreaSweep, Event, EventSource, Venue
from nightlife.sweep_area import compute_diff, resolve_bairro, run_sweep


def test_resolve_bairro_normaliza_e_casa_substring():
    label, lat, lng = resolve_bairro("augusta")
    assert "Augusta" in label
    assert lat == pytest.approx(-23.55, abs=0.02)
    with pytest.raises(ValueError):
        resolve_bairro("atlantida")   # inexistente lista os validos


def test_resolve_bairro_prefere_match_mais_especifico_no_empate():
    # B10: "baixa augusta" so casa com a semente "Baixa Augusta/Consolacao";
    # "augusta" casa com as duas, mas deve vencer a mais curta (mais especifica).
    label, _, _ = resolve_bairro("baixa augusta")
    assert label == "Baixa Augusta/Consolacao"
    label2, _, _ = resolve_bairro("augusta")
    assert "Augusta" in label2


def test_compute_diff_conta_festas_novas_e_venues_com_primeiro_pin(session):
    v_novo = Venue(name="Aura", instagram="aura", lat=-23.55, lng=-46.66, confidence=50)
    v_velho = Venue(name="Blitz", instagram="blitz", lat=-23.552, lng=-46.652, confidence=50)
    session.add_all([v_novo, v_velho])
    session.flush()
    antes_evt = Event(name="Antiga", status="scheduled", confidence=40, venue_id=v_velho.id,
                      starts_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
    session.add(antes_evt)
    session.flush()
    from nightlife.sweep_area import snapshot_future
    before = snapshot_future(session)
    nova1 = Event(name="Nova no Aura", status="scheduled", confidence=40, venue_id=v_novo.id,
                  starts_at=datetime(2099, 2, 1, tzinfo=timezone.utc))
    nova2 = Event(name="Nova no Blitz", status="scheduled", confidence=40, venue_id=v_velho.id,
                  starts_at=datetime(2099, 2, 2, tzinfo=timezone.utc))
    session.add_all([nova1, nova2])
    session.flush()
    diff = compute_diff(session, before)
    assert diff["novas_festas"] == 2
    assert diff["venues_com_pin_novo"] == ["Aura"]   # Blitz ja tinha festa


def test_run_sweep_preenche_report_e_nao_derruba_por_handle_com_falha(session, tmp_path):
    v1 = Venue(name="Aura", instagram="aura", lat=-23.55, lng=-46.66, confidence=50)
    v2 = Venue(name="Quebrado", instagram="quebrado", lat=-23.551, lng=-46.661, confidence=50)
    session.add_all([v1, v2])
    session.flush()
    sweep = AreaSweep(center_lat=-23.55, center_lng=-46.66, radius_km=2.0,
                      started_at=datetime.now(timezone.utc))
    session.add(sweep)
    session.flush()

    def fake_scrape(handle, state):
        if handle == "quebrado":
            raise RuntimeError("boom")
        (tmp_path / "SC1.jpg").write_bytes(b"x")
        (tmp_path / "SC1.json").write_text('{"handle": "aura"}')
        return SimpleNamespace(downloaded=1, last_shortcode="SC1",
                               latest_post_at=datetime.now(timezone.utc))

    def fake_extract():
        # simula a extracao criando um evento ancorado com permalink do SC1
        from nightlife.models import EventSource
        ev = Event(name="Festa do Aura", status="scheduled", confidence=40, venue_id=v1.id,
                   starts_at=datetime(2099, 3, 1, tzinfo=timezone.utc))
        session.add(ev)
        session.flush()
        session.add(EventSource(event_id=ev.id, source_type="vision_flyer",
                                source_url="https://www.instagram.com/p/SC1/"))
        session.flush()

    run_sweep(session, sweep, inbox=tmp_path, scrape=fake_scrape, extract=fake_extract,
              delay=lambda: None)

    assert sweep.status == "done"
    assert sweep.phase == "done"
    assert sweep.total_handles == 2
    by_handle = {i["handle"]: i for i in sweep.report}
    assert by_handle["aura"]["status"] == "ok"
    assert by_handle["aura"]["posts_novos"] == 1
    assert by_handle["aura"]["flyers"] == ["SC1"]
    assert by_handle["aura"]["festas"][0]["name"] == "Festa do Aura"
    assert by_handle["aura"]["festas"][0]["anchored"] is True
    assert by_handle["quebrado"]["status"] == "falha"
    assert sweep.diff["novas_festas"] == 1


def test_events_for_shortcodes_nao_casa_por_prefixo_like(session):
    # B5: LIKE '%/p/{sc}%' faria '/p/SC1' casar com '/p/SC12/' tambem — o
    # shortcode precisa bater EXATO (regex + dict), nao por substring.
    from nightlife.sweep_area import _events_for_shortcodes
    ev_curto = Event(name="Curto", status="scheduled", confidence=40,
                     starts_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
    ev_longo = Event(name="Longo", status="scheduled", confidence=40,
                     starts_at=datetime(2099, 1, 2, tzinfo=timezone.utc))
    session.add_all([ev_curto, ev_longo])
    session.flush()
    session.add_all([
        EventSource(event_id=ev_curto.id, source_type="vision_flyer",
                   source_url="https://www.instagram.com/p/SC1/"),
        EventSource(event_id=ev_longo.id, source_type="vision_flyer",
                   source_url="https://www.instagram.com/p/SC12/"),
    ])
    session.flush()

    out = _events_for_shortcodes(session, ["SC1"])

    assert [o["event_id"] for o in out] == [ev_curto.id]
