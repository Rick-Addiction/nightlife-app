# tests/test_codex_extractor.py
import json
from pathlib import Path

from nightlife.ingestion.codex_extractor import CodexExtractor

GOOD_JSON = json.dumps({
    "event_name": "MAMBA NEGRA", "date_text": "SEX 13/06 23h",
    "venue_name": "Lab Club", "organizer": None, "lineup": [],
    "price_text": None, "ticket_url": None, "instagram_handle": None,
    "quotes": {"event_name": "MAMBA NEGRA"}, "confidence": {"event_name": 0.9},
})


def test_extracts_from_wrapped_output(tmp_path):
    # CLIs de agente cercam o JSON de logs/preambulo: extrair do 1o { ao ultimo }
    calls = []

    def fake_runner(image_path, prompt):
        calls.append(prompt)
        return f"thinking...\nsegue o resultado:\n{GOOD_JSON}\nfim."

    ext = CodexExtractor(runner=fake_runner)
    result = ext.extract(tmp_path / "flyer.png")
    assert result is not None and result.event_name == "MAMBA NEGRA"
    assert len(calls) == 1


def test_retry_once_on_invalid_then_success(tmp_path):
    outputs = ["isso nao e json", GOOD_JSON]
    calls = []

    def fake_runner(image_path, prompt):
        calls.append(prompt)
        return outputs[len(calls) - 1]

    result = CodexExtractor(runner=fake_runner).extract(tmp_path / "f.png")
    assert result is not None
    assert len(calls) == 2
    assert "invalida" in calls[1].lower()  # o retry anexa o motivo


def test_gives_up_after_retry(tmp_path):
    result = CodexExtractor(runner=lambda p, q: "lixo sem json").extract(tmp_path / "f.png")
    assert result is None
