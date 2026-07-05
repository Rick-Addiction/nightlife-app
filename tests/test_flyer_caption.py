from datetime import date
from pathlib import Path

from nightlife.extraction.flyer import FlyerExtraction, flyer_to_raw_event
from nightlife.ingestion.codex_extractor import CodexExtractor

REF = date(2026, 6, 1)


def test_permalink_vira_source_url():
    ext = FlyerExtraction(event_name="Mamba", quotes={"event_name": "Mamba"},
                          confidence={"event_name": 0.9})
    ev = flyer_to_raw_event(ext, "hash123", reference=REF,
                            permalink="https://www.instagram.com/p/ABC/")
    assert ev is not None
    assert ev.source_url == "https://www.instagram.com/p/ABC/"


def test_sem_permalink_mantem_id_sintetico():
    ext = FlyerExtraction(event_name="Mamba", quotes={"event_name": "Mamba"},
                          confidence={"event_name": 0.9})
    ev = flyer_to_raw_event(ext, "hash123", reference=REF)
    assert ev.source_url == "flyer:hash123"


def test_caption_vai_no_prompt_do_codex():
    captured = {}

    def fake_runner(image_path, prompt):
        captured["prompt"] = prompt
        return '{"event_name": "Mamba", "quotes": {"event_name":"Mamba"}, "confidence": {"event_name":0.9}}'

    ext = CodexExtractor(runner=fake_runner)
    ext.extract(Path("f.png"), caption="Sabado 13/06 na Lab, line-up @deusa")
    assert "Sabado 13/06 na Lab" in captured["prompt"]
    assert "legenda" in captured["prompt"].lower()


def test_extract_sem_caption_funciona():
    def fake_runner(image_path, prompt):
        return '{"event_name": "X", "quotes": {"event_name":"X"}, "confidence": {"event_name":0.9}}'
    assert CodexExtractor(runner=fake_runner).extract(Path("f.png")) is not None
