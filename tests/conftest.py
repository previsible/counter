"""
Shared pytest fixtures.

Uses an in-memory SQLite database so tests are fast and isolated.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Food, DiaryEntry, Exercise  # noqa: F401 — register models


TEST_DATABASE_URL = "sqlite://"  # pure in-memory


@pytest.fixture(scope="function")
def db_engine():
    # StaticPool forces all connections to reuse the same underlying connection
    # so the in-memory database is shared across all sessions within a test.
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_engine):
    """FastAPI TestClient with the in-memory DB wired in."""
    Session = sessionmaker(bind=db_engine)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_food(db_session):
    """A pre-saved food for use in tests.

    NOTE: tests that need both `client` and `sample_food` must use the
    `client_with_food` fixture below, which inserts via the API so the
    data is visible to the same DB session the client uses.
    """
    food = Food(
        name="chicken sandwich",
        calories=450,
        protein_g=35.0,
        carbs_g=40.0,
        fat_g=12.0,
        unit="serving",
        aliases="chicken sarnie,chick sandwich",
    )
    db_session.add(food)
    db_session.commit()
    db_session.refresh(food)
    return food


class _FoodProxy:
    """Minimal stand-in returned by client_with_food, mimicking Food attributes."""
    def __init__(self, data: dict):
        self.__dict__.update(data)


@pytest.fixture
def client_with_food(client):
    """Client fixture that also inserts a sample food via the API."""
    r = client.post("/api/foods", json={
        "name": "chicken sandwich",
        "calories": 450,
        "protein_g": 35.0,
        "carbs_g": 40.0,
        "fat_g": 12.0,
        "unit": "serving",
        "aliases": "chicken sarnie,chick sandwich",
    })
    assert r.status_code == 201, r.text
    food = _FoodProxy(r.json())
    return client, food
