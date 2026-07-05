# tests/test_flyer_source.py
import shutil
from datetime import date

from PIL import Image

from nightlife.extraction.flyer import FlyerExtraction
from nightlife.ingestion.flyer_source import FlyerSource

REF = date(2026, 6, 1)


def _img(path, seed=0):
    img = Image.new("L", (80, 60))
    img.putdata([(x * (seed + 1) + y) % 256 for y in range(60) for x in range(80)])
    img.save(path)
    return path


class _FakeExtractor:
    def __init__(self, results):
        self.results = results  # por nome de arquivo
        self.calls = []

    def extract(self, image_path, *, caption=None):
        self.calls.append(image_path.name)
        return self.results.get(image_path.name)


def _extraction(name="Festa X"):
    return FlyerExtraction(event_name=name, date_text="13/06 23h",
                           quotes={"event_name": name}, confidence={"event_name": 0.9})


def test_scans_dedupes_and_tracks_paths(tmp_path):
    a = _img(tmp_path / "a.png", seed=1)
    _img(tmp_path / "b.png", seed=2)
    shutil.copy(a, tmp_path / "a_repost.png")   # mesmo conteudo, outro nome
    (tmp_path / "notas.txt").write_text("nao e imagem")

    fake = _FakeExtractor({"a.png": _extraction("Festa A"), "b.png": _extraction("Festa B")})
    src = FlyerSource(tmp_path, fake, reference=REF)
    events = src.events()

    assert sorted(fake.calls) == ["a.png", "b.png"]          # repost NAO gastou extracao
    assert sorted(e.name for e in events) == ["Festa A", "Festa B"]
    assert all(e.source_type == "vision_flyer" for e in events)
    assert sorted(p.name for p in src.processed_paths) == ["a.png", "a_repost.png", "b.png"]
    assert src.failed_paths == []
    assert src.venues() == [] and src.event_pages() == []


def test_failed_extraction_goes_to_failed(tmp_path):
    _img(tmp_path / "ruim.png", seed=3)
    fake = _FakeExtractor({})  # extractor devolve None
    src = FlyerSource(tmp_path, fake, reference=REF)
    assert src.events() == []
    assert [p.name for p in src.failed_paths] == ["ruim.png"]
    assert src.processed_paths == []


import json


def test_le_sidecar_e_passa_caption_e_permalink(tmp_path):
    _img(tmp_path / "P3.png", seed=5)
    (tmp_path / "P3.json").write_text(json.dumps({
        "handle": "mambanegra", "permalink": "https://www.instagram.com/p/P3/",
        "caption": "Sabado 13/06 na Lab", "taken_at": 1717800000,
    }), encoding="utf-8")

    seen = {}

    class _Extractor:
        def extract(self, image_path, *, caption=None):
            seen["caption"] = caption
            return _extraction("Mamba")

    src = FlyerSource(tmp_path, _Extractor(), reference=REF)
    events = src.events()
    assert seen["caption"] == "Sabado 13/06 na Lab"          # legenda repassada
    assert events[0].source_url == "https://www.instagram.com/p/P3/"  # permalink vira evidencia
