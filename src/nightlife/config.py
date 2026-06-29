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
