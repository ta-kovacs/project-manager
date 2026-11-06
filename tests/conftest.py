import os

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
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
from app.storage import LocalStorage, S3Storage, get_storage

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

# Which storage backend the API tests use: "local" (default) or "s3" (a moto-mocked bucket).
# CI runs the suite with both.
TEST_STORAGE_BACKEND = os.getenv("TEST_STORAGE_BACKEND", "local")
TEST_BUCKET = "test-project-documents"
TEST_REGION = "eu-north-1"


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
def s3_bucket():
    """Name of the mocked S3 bucket that `s3_client` creates."""
    return TEST_BUCKET


@pytest.fixture
def s3_client(monkeypatch):
    """A boto3 S3 client against moto's in-memory S3, with an empty TEST_BUCKET.

    Fake credentials are set so that no request can ever reach a real AWS account.
    """
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", TEST_REGION)
    with mock_aws():
        client = boto3.client("s3", region_name=TEST_REGION)
        client.create_bucket(Bucket=TEST_BUCKET, CreateBucketConfiguration={"LocationConstraint": TEST_REGION})
        yield client


def _make_storage(backend, request, tmp_path):
    if backend == "s3":
        return S3Storage(TEST_BUCKET, client=request.getfixturevalue("s3_client"))
    return LocalStorage(tmp_path / "storage")


@pytest.fixture
def storage(request, tmp_path):
    """Document file storage for the test: TEST_STORAGE_BACKEND decides local disk or mocked S3."""
    return _make_storage(TEST_STORAGE_BACKEND, request, tmp_path)


@pytest.fixture(params=["local", "s3"])
def any_storage(request, tmp_path):
    """Each storage backend in turn; tests using it run once per backend."""
    return _make_storage(request.param, request, tmp_path)


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
def make_document(db_session, storage):
    """Attach a PDF to a project, with its file in `storage`; returns the Document.

    Inserted directly, so tests of other endpoints don't depend on the upload endpoint.
    """
    def _make_document(project_id, *, filename="spec.pdf", content=b"%PDF-1.4 test document"):
        document = Document(
            project_id=project_id,
            storage_key=f"projects/{project_id}/documents/{filename}",
            original_filename=filename,
            content_type="application/pdf",
        )
        storage.save(document.storage_key, content, "application/pdf")
        db_session.add(document)
        db_session.commit()
        return document

    return _make_document


@pytest.fixture
def document(project, make_document, document_content):
    """A PDF attached to `project`, with its file in `storage`."""
    return make_document(project["id"], content=document_content)


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


@pytest.fixture
def list_project_documents(client, auth):
    """GET /project/{id}/documents as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _list_project_documents(project_id, *, auth=default_auth):
        return client.get(f"/project/{project_id}/documents", auth=auth)

    return _list_project_documents


@pytest.fixture
def upload_files():
    """Valid files for one upload, as (filename, content) pairs."""
    return [("report.pdf", b"%PDF-1.4 report"), ("notes.docx", b"PK\x03\x04 notes")]


@pytest.fixture
def upload_documents(client, auth, upload_files):
    """POST /project/{id}/documents as the default user, uploading `upload_files`; pass `files` to
    upload others ([] for none), `auth` for other credentials (None for none)."""
    default_auth = auth

    def _upload_documents(project_id, *, auth=default_auth, files=None):
        files = upload_files if files is None else files
        multipart = [("files", (name, content)) for name, content in files] or None
        return client.post(f"/project/{project_id}/documents", files=multipart, auth=auth)

    return _upload_documents


@pytest.fixture
def stored_files(storage):
    """Returns the keys of all files currently in `storage` (either backend)."""
    def _stored_files():
        if isinstance(storage, S3Storage):
            response = storage.client.list_objects_v2(Bucket=storage.bucket)
            return [item["Key"] for item in response.get("Contents", [])]
        if not storage.root.exists():
            return []
        return [path.relative_to(storage.root).as_posix() for path in storage.root.rglob("*") if path.is_file()]

    return _stored_files
