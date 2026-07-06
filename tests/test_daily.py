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
