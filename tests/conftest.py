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
from app.models.document import Document
from app.models.project_user import ProjectRole, ProjectUser
from app.models.user import User
from app.routes import documents as document_routes
from app.services import document_service
from app.storage import LocalStorage, get_storage

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
def storage(tmp_path):
    """Document file storage in a per-test temporary directory."""
    return LocalStorage(tmp_path / "storage")


@pytest.fixture
def client(db_session, storage):
    """API client whose requests use the test database and test storage."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = lambda: storage
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


@pytest.fixture
def project(create_project):
    """A project owned by the default user; returns its POST /projects response body."""
    response = create_project()
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def participant_auth(project, other_auth, db_session):
    """Credentials of the second user, added to `project` as a participant.

    There is no invite endpoint yet, so the membership is inserted directly.
    """
    other_user = db_session.query(User).filter_by(username=other_auth[0]).one()
    db_session.add(ProjectUser(project_id=project["id"], user_id=other_user.id, role=ProjectRole.PARTICIPANT))
    db_session.commit()
    return other_auth


@pytest.fixture
def get_project_info(client, auth):
    """GET /project/{id}/info as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _get_project_info(project_id, *, auth=default_auth):
        return client.get(f"/project/{project_id}/info", auth=auth)

    return _get_project_info


@pytest.fixture
def updated_data():
    """Valid replacement details for a project."""
    return {"name": "Artemis", "description": "Back to the moon"}


@pytest.fixture
def update_project_info(client, auth, updated_data):
    """PUT /project/{id}/info as the default user; pass fields to override them, `exclude` to leave
    some out, `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _update_project_info(project_id, *, auth=default_auth, exclude=(), **overrides):
        return client.put(
            f"/project/{project_id}/info",
            json=_payload(updated_data, overrides, exclude),
            auth=auth,
        )

    return _update_project_info


@pytest.fixture
def document_content():
    """Bytes of the `document` fixture's file."""
    return b"%PDF-1.4 test document"


@pytest.fixture
def document(project, db_session, storage, document_content):
    """A PDF attached to `project`, with its file in `storage`.

    Inserted directly as there is no upload endpoint yet.
    """
    document = Document(
        project_id=project["id"],
        storage_key=f"projects/{project['id']}/documents/spec",
        original_filename="spec.pdf",
        content_type="application/pdf",
    )
    storage.save(document.storage_key, document_content)
    db_session.add(document)
    db_session.commit()
    return document


@pytest.fixture
def delete_project(client, auth):
    """DELETE /project/{id} as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _delete_project(project_id, *, auth=default_auth):
        return client.delete(f"/project/{project_id}", auth=auth)

    return _delete_project


# --- documents ---------------------------------------------------------------

@pytest.fixture
def download_document(client, auth):
    """GET /document/{id} as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _download_document(document_id, *, auth=default_auth):
        return client.get(f"/document/{document_id}", auth=auth)

    return _download_document


@pytest.fixture
def new_file():
    """A valid replacement file for a document."""
    return {"filename": "report.docx", "content": b"PK\x03\x04 test docx"}


@pytest.fixture
def replace_document(client, auth, new_file):
    """PUT /document/{id} as the default user, uploading `new_file`; pass `filename`/`content` to
    override it, `exclude=["file"]` to send no file, `auth` for other credentials (None for none)."""
    default_auth = auth

    def _replace_document(document_id, *, auth=default_auth, exclude=(), **overrides):
        upload = {**new_file, **overrides}
        files = None if "file" in exclude else {"file": (upload["filename"], upload["content"])}
        return client.put(f"/document/{document_id}", files=files, auth=auth)

    return _replace_document


@pytest.fixture
def max_document_size(monkeypatch):
    """Lowers the document size limit to 16 bytes for the test; returns the limit."""
    limit = 16
    monkeypatch.setattr(document_service, "MAX_DOCUMENT_SIZE", limit)
    monkeypatch.setattr(document_routes, "MAX_DOCUMENT_SIZE", limit)
    return limit


@pytest.fixture
def delete_document(client, auth):
    """DELETE /document/{id} as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _delete_document(document_id, *, auth=default_auth):
        return client.delete(f"/document/{document_id}", auth=auth)

    return _delete_document
