"""PROBE (Ciclo E-3, gate): abre a sessao da burner, vai ao feed, captura TODAS
as respostas JSON e salva as que parecem timeline de feed. Objetivo: descobrir o
shape (chave da connection + onde vem o @autor de cada post) pra ancorar o
parser. NAO roda em CI — e uma investigacao manual assistida.

Uso: .venv/Scripts/python -m nightlife.probe_feed
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .ingestion.instagram_source import open_context

OUT = Path("tests/fixtures")


def _keys(d, depth=0):
    if depth > 4 or not isinstance(d, dict):
        return
    for k, v in d.items():
        yield k
        if isinstance(v, dict):
            yield from _keys(v, depth + 1)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
    captured: list[dict] = []
    try:
        page = context.new_page()

        def _on_response(resp):
            if "application/json" not in resp.headers.get("content-type", ""):
                return
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                return
            if isinstance(data, dict):
                captured.append(data)

        page.on("response", _on_response)
        # feed "Seguindo" cronologico (agora que a burner segue venues). Mesma
        # connection do home; o no dos posts seguidos e o que queremos travar.
        page.goto("https://www.instagram.com/?variant=following",
                  wait_until="domcontentloaded", timeout=45000)
        for _ in range(4):
            page.wait_for_timeout(3500)
            page.mouse.wheel(0, 4000)      # rola pra disparar mais requests do feed
        page.wait_for_timeout(2500)
        page.close()
    finally:
        context.close()
        pw.stop()

    hits = [d for d in captured
            if any(k for k in _keys(d) if "feed" in k or "timeline" in k)]
    (OUT / "feed_probe_raw.json").write_text(
        json.dumps(hits[:5], ensure_ascii=False, indent=2), encoding="utf-8")
    # tambem lista as chaves de topo de cada resposta capturada (mapa do terreno)
    resumo = [sorted(set(k for k in _keys(d)))[:40] for d in captured]
    (OUT / "feed_probe_keys.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"capturei {len(captured)} respostas JSON; {len(hits)} com cara de feed.")
    print(f"salvo em {OUT / 'feed_probe_raw.json'} e feed_probe_keys.json")


if __name__ == "__main__":
    main()
