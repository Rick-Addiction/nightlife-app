from nightlife.daily import StepResult, run_daily, any_failed


def test_run_daily_roda_em_ordem_e_agrega():
    calls = []
    logs = []

    def fake_run(name, argv):
        calls.append(name)
        return StepResult(name=name, ok=True, output=f"out-{name}")

    steps = [("a", ["x"]), ("b", ["y"]), ("c", ["z"])]
    results = run_daily(steps, run=fake_run, log=logs.append)
    assert calls == ["a", "b", "c"]
    assert [r.name for r in results] == ["a", "b", "c"]
    assert not any_failed(results)


def test_run_daily_isola_falha():
    calls = []

    def fake_run(name, argv):
        calls.append(name)
        return StepResult(name=name, ok=(name != "b"))   # b falha

    results = run_daily([("a", ["x"]), ("b", ["y"]), ("c", ["z"])],
                        run=fake_run, log=lambda m: None)
    assert calls == ["a", "b", "c"]              # c roda mesmo com b falhando
    assert any_failed(results)
    assert [r.ok for r in results] == [True, False, True]


def test_run_daily_executor_que_levanta_nao_aborta():
    # se o executor LEVANTA (nao so retorna ok=False), o best-effort ainda segue
    calls = []

    def boom(name, argv):
        calls.append(name)
        if name == "b":
            raise RuntimeError("crash inesperado")
        return StepResult(name=name, ok=True)

    results = run_daily([("a", ["x"]), ("b", ["y"]), ("c", ["z"])],
                        run=boom, log=lambda m: None)
    assert calls == ["a", "b", "c"]                  # c roda apesar do crash em b
    assert [r.ok for r in results] == [True, False, True]
    assert "erro inesperado" in results[1].output


def test_run_daily_loga_por_passo():
    logs = []
    run_daily([("a", ["x"])], run=lambda n, a: StepResult(n, True), log=logs.append)
    assert any("a" in m for m in logs)


import sys
from nightlife.daily import _run_step


def test_run_step_ok():
    r = _run_step("echo", [sys.executable, "-c", "print('oi')"])
    assert r.ok is True
    assert "oi" in r.output


def test_run_step_falha_em_returncode_nao_zero():
    r = _run_step("fail", [sys.executable, "-c", "import sys; sys.exit(3)"])
    assert r.ok is False


def test_run_step_erro_ao_iniciar():
    r = _run_step("nope", ["programa_que_nao_existe_xyz_123"])
    assert r.ok is False
    assert "erro ao iniciar" in r.output


def test_steps_inclui_ra():
    from nightlife.daily import STEPS
    nomes = [nome for nome, argv in STEPS]
    assert "ingest_ra" in nomes
    # ra vem antes do geocoding (venues do RA ancoram antes de geocodificar)
    assert nomes.index("ingest_ra") < nomes.index("geocode_venues")


def test_steps_inclui_sympla():
    # regressao do smoke C-2: Sympla ficou FORA do daily desde que o daily
    # nasceu (so tinha discover/ig/flyers; RA entrou depois, Sympla nunca) —
    # eventos de ticketing congelaram no seed de 2026-07-04
    from nightlife.daily import STEPS
    nomes = [nome for nome, argv in STEPS]
    assert "ingest_sympla" in nomes
    # sympla tambem ancora venues/organizers antes do geocoding
    assert nomes.index("ingest_sympla") < nomes.index("geocode_venues")


def test_ingest_ig_saiu_do_daily_diario():
    # E-3: a varredura cega vira reconciliacao SEMANAL, fora do daily das 05h
    from nightlife.daily import STEPS
    nomes = [nome for nome, argv in STEPS]
    assert "ingest_ig" not in nomes
    assert "ingest_flyers" in nomes          # extracao do inbox continua diaria
    assert "discover_handles" in nomes


def test_steps_inclui_shotgun():
    # fonte #4 (Shotgun) entra no daily depois da Sympla e antes do geocoding,
    # pra os venues novos dela serem geocodificados na mesma rodada
    from nightlife.daily import STEPS
    nomes = [nome for nome, argv in STEPS]
    assert "ingest_shotgun" in nomes
    assert nomes.index("ingest_sympla") < nomes.index("ingest_shotgun") < nomes.index("geocode_venues")
