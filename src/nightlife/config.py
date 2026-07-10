# src/nightlife/config.py
from __future__ import annotations

import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://nightlife:nightlife@localhost:5434/nightlife?sslmode=disable&gssencmode=disable",
)
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://nightlife:nightlife@localhost:5434/nightlife_test?sslmode=disable&gssencmode=disable",
)

from pathlib import Path

# Instagram scraper (spec §8) — defaults conservadores
IG_USER_DATA_DIR = Path(os.environ.get("IG_USER_DATA_DIR", ".ig_session"))
IG_HEADFUL = os.environ.get("IG_HEADFUL", "1") != "0"
# cap por rodada (Ciclo B): ~300 handles -> passada completa em ~15 dias
IG_MAX_PROFILES_PER_RUN = int(os.environ.get("IG_MAX_PROFILES_PER_RUN", "20"))
IG_MAX_POSTS_FIRST_SWEEP = int(os.environ.get("IG_MAX_POSTS_FIRST_SWEEP", "6"))
IG_MAX_POSTS_INCREMENTAL = int(os.environ.get("IG_MAX_POSTS_INCREMENTAL", "12"))
IG_DELAY_MIN = float(os.environ.get("IG_DELAY_MIN", "4"))
IG_DELAY_MAX = float(os.environ.get("IG_DELAY_MAX", "11"))
IG_FAILURE_PAUSE_THRESHOLD = int(os.environ.get("IG_FAILURE_PAUSE_THRESHOLD", "3"))

# Google Geocoding API (endereco -> coordenada). Chave criada pelo usuario no
# Google Cloud (Geocoding API + billing). Sem ela, o runner de geocoding aborta.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY") or None

# Flyers processados (Ciclo B) servidos pela API em /flyers (Ciclo C)
FLYERS_PROCESSED_DIR = Path(os.environ.get("FLYERS_DIR", "flyers")) / "processed"
