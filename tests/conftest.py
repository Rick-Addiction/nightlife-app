# tests/conftest.py
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nightlife.config import TEST_DATABASE_URL, DATABASE_URL
from nightlife import db as db_module
from nightlife.db import Base
import nightlife.models  # noqa: F401  (registra os models no metadata)


def _ensure_test_database():
    """Cria o database de teste se nao existir (CREATE DATABASE exige autocommit)."""
    admin = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = 'nightlife_test'")
            ).scalar()
            if not exists:
                conn.execute(text("CREATE DATABASE nightlife_test"))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def engine():
    _ensure_test_database()
    eng = create_engine(TEST_DATABASE_URL, future=True)
    db_module.engine = eng
    db_module.SessionLocal.configure(bind=eng)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    """Sessao isolada por teste: tudo e revertido no fim (nada persiste)."""
    conn = engine.connect()
    trans = conn.begin()
    sess = Session(bind=conn, join_transaction_mode="create_savepoint", future=True)
    try:
        yield sess
    finally:
        sess.close()
        trans.rollback()
        conn.close()
