import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.database import get_db
from app.main import app
from app.models.base import Base

# CI points this at a throwaway Postgres; locally the tests fall back to in-memory SQLite.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")

if TEST_DATABASE_URL.startswith("sqlite"):
    # One shared connection so every session sees the same in-memory database.
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(TEST_DATABASE_URL)

TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# --- database and client -----------------------------------------------------

@pytest.fixture
def db_session():
    """A fresh, empty schema for each test."""
    Base.metadata.create_all(engine)
    try:
        with TestingSessionLocal() as session:
            yield session
    finally:
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    """API client whose requests use the test database."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


# --- auth --------------------------------------------------------------------

@pytest.fixture
def credentials():
    """Valid credentials of the default test user."""
    return {"username": "alice", "password": "s3cret-pass"}


def _payload(base, overrides, exclude):
    payload = {**base, **overrides}
    for field in exclude:
        payload.pop(field)
    return payload


@pytest.fixture
def register(client, credentials):
    """POST /auth with valid data; pass fields to override them, `exclude` to leave some out.

    `repeat_password` follows `password` unless it is overridden itself.
    """
    def _register(*, exclude=(), **overrides):
        password = overrides.get("password", credentials["password"])
        base = {**credentials, "repeat_password": password}
        return client.post("/auth", json=_payload(base, overrides, exclude))

    return _register


@pytest.fixture
def login(client, credentials):
    """POST /login with valid credentials; pass fields to override them, `exclude` to leave some out."""
    def _login(*, exclude=(), **overrides):
        return client.post("/login", json=_payload(credentials, overrides, exclude))

    return _login


@pytest.fixture
def registered_user(register):
    """The default test user, already registered; returns the POST /auth response body."""
    response = register()
    assert response.status_code == 201, response.text
    return response.json()


# --- projects ----------------------------------------------------------------

@pytest.fixture
def auth(registered_user, credentials):
    """HTTP Basic credentials of the registered default user, for protected endpoints."""
    return (credentials["username"], credentials["password"])


@pytest.fixture
def other_auth(register):
    """HTTP Basic credentials of a second registered user."""
    response = register(username="bob", password="bobs-password")
    assert response.status_code == 201, response.text
    return ("bob", "bobs-password")


@pytest.fixture(
    params=[
        pytest.param(None, id="no-credentials"),
        pytest.param(("alice", "wrong-password"), id="wrong-password"),
        pytest.param(("nobody", "s3cret-pass"), id="unknown-username"),
    ]
)
def bad_auth(request, registered_user):
    """Each way a protected request can fail to authenticate; tests using it run once per case."""
    return request.param


@pytest.fixture
def project_data():
    """Valid data for a new project."""
    return {"name": "Apollo", "description": "Land on the moon"}


@pytest.fixture
def create_project(client, auth, project_data):
    """POST /projects as the default user; pass fields to override them, `exclude` to leave some out,
    `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _create_project(*, auth=default_auth, exclude=(), **overrides):
        return client.post("/projects", json=_payload(project_data, overrides, exclude), auth=auth)

    return _create_project


@pytest.fixture
def list_projects(client, auth):
    """GET /projects as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _list_projects(*, auth=default_auth):
        return client.get("/projects", auth=auth)

    return _list_projects
