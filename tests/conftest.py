import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from config import Settings
from common.db import Base
from db.session import Database


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
        cookie_signing_secret="test-signing-secret",
        rate_limit_default_per_minute=1000,  # high, so rate limiting doesn't interfere with unrelated tests
    )


@pytest.fixture
def db(settings: Settings) -> Database:
    database = Database(settings)
    Base.metadata.create_all(database.engine)
    return database


@pytest.fixture
def db_session(db: Database):
    session = db.session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def app(settings: Settings, db: Database):
    application = create_app(settings)
    # Swap in the already-table-populated Database from the db fixture,
    # since create_app() builds its own — tests need the one with
    # Base.metadata.create_all already applied.
    application.state.database = db
    return application


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)
