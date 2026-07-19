"""
Test fixtures — runs inside the Docker `test` service against real Postgres.

Start with:
    docker compose --profile test run --rm test

Each test gets its own DB session that is rolled back after the test,
so tests are isolated without dropping/recreating the schema.
SMTP and subprocess (plantbgc) are always patched — no real emails sent,
no real analysis runs.
"""
import os
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from src.database import Base, get_db
from src.main import app

DATABASE_URL = os.environ["DATABASE_URL"]

_engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base.metadata.create_all(bind=_engine)   # idempotent — creates tables if missing
_SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db_session():
    session = _SessionFactory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def client(db_session, tmp_path, monkeypatch):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    monkeypatch.setattr("src.main.send_queued_email", lambda *a, **kw: None)

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
