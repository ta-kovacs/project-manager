"""The app under test and what it runs on: database, document storage, mailer and the API client."""
import os

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # registers every model on Base.metadata
from app.database import get_db
from app.mailer import get_mailer
from app.main import app
from app.models.base import Base
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


class RecordingMailer:
    """Keeps sent emails in `sent` instead of delivering them."""

    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body})


@pytest.fixture
def mailer():
    """The mailer the API uses in tests; inspect `mailer.sent`."""
    return RecordingMailer()


@pytest.fixture
def client(db_session, storage, mailer):
    """API client whose requests use the test database, storage and mailer."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_mailer] = lambda: mailer
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
