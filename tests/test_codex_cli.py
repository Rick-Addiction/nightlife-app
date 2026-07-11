# tests/test_codex_cli.py
"""Cobertura da plomberia compartilhada do codex CLI (movida de
test_codex_extractor.py no Task 6 — CodexExtractor saiu, mas as licoes de
Windows/seguranca de run_codex/extract_json continuam valendo pro
PostInterpreter)."""
import json

from PIL import Image

from nightlife.ingestion import codex_cli


GOOD_JSON = json.dumps({"actions": []})


def test_extract_json_extrai_do_meio_de_texto_cercado():
    # CLIs de agente cercam o JSON de logs/preambulo: extrair do 1o { ao ultimo }
    out = codex_cli.extract_json(f"thinking...\nsegue o resultado:\n{GOOD_JSON}\nfim.")
    assert out == {"actions": []}


def test_run_codex_isolates_untrusted_filename_and_stdin_prompt(tmp_path, monkeypatch):
    # nome de arquivo com metacaractere de shell NAO pode chegar ao argv;
    # o prompt (multi-linha) vai por stdin
    evil = tmp_path / "a&whoami&b.png"
    Image.new("RGB", (10, 10), "#111").save(evil)

    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs

        class _R:
            stdout = '{"actions": []}'
        return _R()

    monkeypatch.setattr(codex_cli.subprocess, "run", fake_run)
    codex_cli.run_codex(evil, "PROMPT\nMULTI\nLINHA")

    assert "whoami" not in " ".join(captured["argv"])   # nome perigoso isolado
    assert captured["kwargs"]["input"] == "PROMPT\nMULTI\nLINHA"  # prompt via stdin
