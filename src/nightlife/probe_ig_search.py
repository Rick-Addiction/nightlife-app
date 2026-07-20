"""PROBE (Ciclo E-2b, gate): busca um nome no IG e captura TODAS as respostas
JSON, salvando as que servem os resultados de usuario. Descobre o shape (onde
vem username/full_name/is_verified/follower_count). NAO roda em CI.
Uso: .venv/Scripts/python -m nightlife.probe_ig_search "Oficina Club"
"""
from __future__ import annotations

import json
import sys
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


_ENDPOINTS = [
    # topsearch classico (users+hashtags+places), context blended
    "https://www.instagram.com/web/search/topsearch/?context=blended&query={q}",
    "https://www.instagram.com/api/v1/web/search/topsearch/?context=blended&query={q}",
]


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "Oficina Club"
    OUT.mkdir(parents=True, exist_ok=True)
    pw, context = open_context(config.IG_USER_DATA_DIR, headful=config.IG_HEADFUL)
    results: dict = {}
    try:
        page = context.new_page()
        # precisa passar pela home logada 1x pra os cookies/headers valerem
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        from urllib.parse import quote
        for tmpl in _ENDPOINTS:
            url = tmpl.format(q=quote(query))
            try:
                resp = context.request.get(url, headers={
                    "X-IG-App-ID": "936619743392459",  # web app id publico
                    "X-Requested-With": "XMLHttpRequest",
                })
                ct = resp.headers.get("content-type", "")
                if resp.ok and "application/json" in ct:
                    results[url] = resp.json()
                    break
                results[url] = {"__status": resp.status, "__ct": ct}
            except Exception as exc:  # noqa: BLE001
                results[url] = {"__error": str(exc)}
        page.close()
    finally:
        context.close()
        pw.stop()

    hits = {u: d for u, d in results.items()
            if isinstance(d, dict) and any(k in d for k in ("users", "list", "num_results"))}
    (OUT / "ig_search_probe_raw.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2)[:200000], encoding="utf-8")
    for u, d in hits.items():
        keys = sorted(set(_keys(d)))
        print(f"OK {u}\n  keys: {keys[:25]}")
    print(f"capturei {len(results)} respostas; {len(hits)} com cara de busca (users/list).")
    print(f"salvo em {OUT / 'ig_search_probe_raw.json'}")


if __name__ == "__main__":
    main()
