# tests/test_post_flow.py
import json
import shutil
from datetime import date, datetime, timedelta, timezone

from PIL import Image

from nightlife.extraction.post_actions import AddEvent, Ignore, PostInterpretation
from nightlife.ingestion.post_flow import _context_for, process_inbox
from nightlife.models import Event, IngestionRun, Venue

REF = date(2026, 7, 11)


class FakeInterpreter:
    def __init__(self, by_stem):
        self.by_stem = by_stem
        self.calls = []

    def interpret(self, doc, ctx):
        self.calls.append((doc, ctx))
        return self.by_stem.get(doc.image_path.stem)


def _img(path, seed=0):
    # imagem PIL real (dhash abre com Image.open) — conteudo varia por seed
    # p/ produzir dHashes distintos por post.
    img = Image.new("L", (80, 60))
    img.putdata([(x * (seed + 1) + y) % 256 for y in range(60) for x in range(80)])
    img.save(path)
    return path


def _post(tmp_path, stem, *, seed=0, handle="selva.011", caption="legenda"):
    _img(tmp_path / f"{stem}.jpg", seed=seed)
    (tmp_path / f"{stem}.json").write_text(json.dumps(
        {"handle": handle, "caption": caption,
         "permalink": f"https://www.instagram.com/p/{stem}/"}), encoding="utf-8")


def test_process_inbox_interpreta_executa_e_separa_paths(session, tmp_path):
    v = Venue(name="Selva Club", instagram="selva.011", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    _post(tmp_path, "OK1", seed=1)
    _post(tmp_path, "IGN1", seed=2)
    _post(tmp_path, "FAIL1", seed=3)
    fake = FakeInterpreter({
        "OK1": PostInterpretation(actions=[AddEvent(
            name="NOITE 1", date_text="SEX 18/07",
            quotes={"name": "NOITE 1", "date_text": "SEX 18/07"},
            confidence={"name": 0.9, "date_text": 0.9})]),
        "IGN1": PostInterpretation(actions=[Ignore(reason="esporte")]),
        # FAIL1 ausente -> interpret devolve None -> failed
    })
    flow = process_inbox(session, tmp_path, fake, reference=REF)
    assert session.query(Event).filter_by(name="NOITE 1").one().venue_id == v.id
    stems_ok = {p.stem for p in flow.processed_paths}
    stems_fail = {p.stem for p in flow.failed_paths}
    assert stems_ok == {"OK1", "IGN1"}
    assert stems_fail == {"FAIL1"}
    assert flow.stats_by_handle["selva.011"]["add"] == 1
    assert flow.stats_by_handle["selva.011"]["ignore"] == {"esporte": 1}
    run = session.query(IngestionRun).order_by(IngestionRun.id.desc()).first()
    assert run.source == "posts"
    assert run.records_created == 1
    # contexto passado ao interprete inclui o venue dono do handle
    assert fake.calls[0][1].venue_name == "Selva Club"
    # legenda do sidecar repassada ao Document (equivalente ao antigo
    # FlyerSource::test_le_sidecar_e_passa_caption_e_permalink)
    assert fake.calls[0][0].caption == "legenda"
    # B4: cada post e movido pro processed/failed IMEDIATAMENTE apos seu
    # commit, nao acumulado ate o fim do inbox inteiro.
    assert (tmp_path / "processed" / "OK1.jpg").exists()
    assert (tmp_path / "processed" / "OK1.json").exists()
    assert (tmp_path / "processed" / "IGN1.jpg").exists()
    assert (tmp_path / "failed" / "FAIL1.jpg").exists()
    assert not (tmp_path / "OK1.jpg").exists()
    assert not (tmp_path / "FAIL1.jpg").exists()


def test_process_inbox_permalink_vira_source_url_e_sem_permalink_usa_hash(session, tmp_path):
    # porte de test_flyer_caption.py (permalink vira source_url / sem
    # permalink mantem id sintetico "flyer:<hash>") pro fluxo novo.
    from nightlife.models import EventSource

    _post(tmp_path, "COMPERM", seed=4)
    _img(tmp_path / "SEMPERM.jpg", seed=5)
    (tmp_path / "SEMPERM.json").write_text(json.dumps({"handle": "selva.011"}),
                                           encoding="utf-8")
    fake = FakeInterpreter({
        "COMPERM": PostInterpretation(actions=[AddEvent(
            name="COM PERMALINK", quotes={"name": "COM PERMALINK"}, confidence={"name": 0.9})]),
        "SEMPERM": PostInterpretation(actions=[AddEvent(
            name="SEM PERMALINK", quotes={"name": "SEM PERMALINK"}, confidence={"name": 0.9})]),
    })
    process_inbox(session, tmp_path, fake, reference=REF)

    ev_com = session.query(Event).filter_by(name="COM PERMALINK").one()
    src_com = session.query(EventSource).filter_by(event_id=ev_com.id).one()
    assert src_com.source_url == "https://www.instagram.com/p/COMPERM/"

    ev_sem = session.query(Event).filter_by(name="SEM PERMALINK").one()
    src_sem = session.query(EventSource).filter_by(event_id=ev_sem.id).one()
    assert src_sem.source_url.startswith("flyer:")


def test_process_inbox_dhash_dedupe_nao_reinterpreta(session, tmp_path):
    _post(tmp_path, "AAA", seed=1)
    shutil.copy(tmp_path / "AAA.jpg", tmp_path / "BBB.jpg")   # mesmo conteudo -> mesmo dHash
    (tmp_path / "BBB.json").write_text("{}", encoding="utf-8")
    fake = FakeInterpreter({"AAA": PostInterpretation(actions=[Ignore(reason="sem_evento")])})
    flow = process_inbox(session, tmp_path, fake, reference=REF)
    assert len(fake.calls) == 1                        # BBB nem chamou o interprete
    assert {p.stem for p in flow.processed_paths} == {"AAA", "BBB"}
    # B4: duplicata tambem e movida (nao so a primeira ocorrencia)
    assert (tmp_path / "processed" / "AAA.jpg").exists()
    assert (tmp_path / "processed" / "BBB.jpg").exists()


def test_context_for_futuro_nao_e_starvado_por_passado(session):
    # B5: o filtro futuro-ou-sem-data precisa estar NO SQL antes do LIMIT —
    # senao 20+ eventos passados enchem o limite e os futuros nunca aparecem.
    v = Venue(name="Selva Club", instagram="selva.011", lat=-23.55, lng=-46.65, confidence=50)
    session.add(v)
    session.flush()
    now = datetime.now(timezone.utc)
    for i in range(25):
        session.add(Event(name=f"PASSADA {i}", status="scheduled", confidence=40,
                          venue_id=v.id, starts_at=now - timedelta(days=i + 1)))
    fut1 = Event(name="FUTURA 1", status="scheduled", confidence=40, venue_id=v.id,
                starts_at=now + timedelta(days=1))
    fut2 = Event(name="FUTURA 2", status="scheduled", confidence=40, venue_id=v.id,
                starts_at=now + timedelta(days=2))
    session.add_all([fut1, fut2])
    session.flush()

    ctx = _context_for(session, "selva.011", date.today())

    assert {n for n, _ in ctx.known_events} == {"FUTURA 1", "FUTURA 2"}


def test_erro_de_db_no_meio_propaga_original_e_run_vira_error(session, tmp_path, monkeypatch):
    # probe do review: excecao de DB abortava a transacao e o commit do finally
    # MASCARAVA o erro original, deixando o run preso em 'running'
    from sqlalchemy import text as _text
    from nightlife.persistence import action_executor as ae

    _post(tmp_path, "BOOM")
    fake = FakeInterpreter({"BOOM": PostInterpretation(actions=[Ignore(reason="sem_evento")])})

    def bad_execute(sess, doc, interp, *, reference):
        sess.execute(_text("SELECT * FROM tabela_que_nao_existe"))

    # process_inbox importa execute_actions DENTRO da funcao: patch no modulo de origem
    monkeypatch.setattr(ae, "execute_actions", bad_execute)
    import pytest as _pytest
    from sqlalchemy.exc import ProgrammingError
    with _pytest.raises(ProgrammingError):        # o erro ORIGINAL, nao o mascarado
        process_inbox(session, tmp_path, fake, reference=REF)
    run = session.query(IngestionRun).order_by(IngestionRun.id.desc()).first()
    assert run.status == "error"
    assert "tabela_que_nao_existe" in (run.errors or "")
