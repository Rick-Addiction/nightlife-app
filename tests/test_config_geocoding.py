import importlib


def test_google_maps_api_key_le_do_ambiente(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "abc123")
    import nightlife.config as cfg
    importlib.reload(cfg)
    assert cfg.GOOGLE_MAPS_API_KEY == "abc123"


def test_google_maps_api_key_default_none(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    import nightlife.config as cfg
    importlib.reload(cfg)
    assert cfg.GOOGLE_MAPS_API_KEY is None
