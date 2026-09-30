import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DEMO_MODE"] = "true"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-secret-for-tests-only-32-characters"

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker
from jc.config import get_settings
from jc.db import make_engine
from jc.db import get_db
from jc.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client(sessions):
    def database():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    if os.environ.get("TEST_DATABASE_URL"):
        from sqlalchemy.engine import make_url
        from sqlalchemy import inspect

        parsed = make_url(url)
        if not parsed.database or not parsed.database.endswith("_test"):
            raise RuntimeError("TEST_DATABASE_URL must name a dedicated database ending in _test")
        check_engine = make_engine(url)
        try:
            if set(inspect(check_engine).get_table_names()) - {"alembic_version"}:
                raise RuntimeError("Refusing to run destructive migration tests in a nonempty database")
        finally:
            check_engine.dispose()
    # TEST_DATABASE_URL must be a disposable dedicated PostgreSQL test database.
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = make_engine(url)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()
    if os.environ.get("TEST_DATABASE_URL"):
        command.downgrade(config, "base")
    get_settings.cache_clear()
