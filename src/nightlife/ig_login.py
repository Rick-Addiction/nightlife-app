# src/nightlife/ig_login.py
"""Bootstrap manual da sessao da conta BURNER (uma vez).

Abre o chromium headful com user-data-dir persistente; VOCE loga a burner a mao
(2FA/challenge inclusos). A sessao fica salva e e reusada pelo ingest_ig.
Uso: .venv/Scripts/python -m nightlife.ig_login
Nenhuma credencial e digitada por codigo (regra de seguranca)."""
from __future__ import annotations

from . import config
from .ingestion.instagram_source import open_context


def main() -> None:
    config.IG_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    pw, context = open_context(config.IG_USER_DATA_DIR, headful=True)
    page = context.new_page()
    page.goto("https://www.instagram.com/accounts/login/")
    print("Loga a conta BURNER na janela do Chromium. Ao terminar, feche a janela.")
    try:
        page.wait_for_event("close", timeout=0)  # espera voce fechar a aba
    except Exception:  # noqa: BLE001
        pass
    context.close()
    pw.stop()
    print(f"Sessao salva em {config.IG_USER_DATA_DIR}")


if __name__ == "__main__":
    main()
