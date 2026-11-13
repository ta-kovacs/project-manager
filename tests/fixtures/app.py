"""The app under test and what it runs on: database, document storage, mailer and the API client."""

import os
from contextlib import contextmanager

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.orm.models  # registers every model on Base.metadata
from app.db.engine import get_db
from app.db.orm import OrmDatabase
from app.db.orm.models.base import Base
from app.db.sql import SqlDatabase
from app.db.sql.connection import connect
from app.db.sql.schema import create_schema, drop_schema
from app.mailer import get_mailer
from app.main import app
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

POSTGRES = engine.dialect.name == "postgresql"

# Which database backend the app uses in the tests: "orm" (default) or "sql" (no ORM, psycopg). CI runs the
# suite with both. Each backend also creates the schema its own way: from the ORM models, or from
# schema.sql. The SQL backend needs PostgreSQL: with the default SQLite database its tests are skipped.
TEST_DATABASE_ACCESS = os.getenv("TEST_DATABASE_ACCESS", "orm")

if TEST_DATABASE_ACCESS == "sql" and not POSTGRES:
    raise RuntimeError("TEST_DATABASE_ACCESS=sql needs PostgreSQL: set TEST_DATABASE_URL to a PostgreSQL database")


def require_postgres():
    """Skip the current test unless the test database is PostgreSQL."""
    if not POSTGRES:
        pytest.skip("needs PostgreSQL (set TEST_DATABASE_URL); the SQL backend runs on psycopg")


@contextmanager
def open_database(access):
    """A Database on the test database, opened the way get_db opens one for each request."""
    if access == "sql":
        connection = connect(TEST_DATABASE_URL)
        try:
            yield SqlDatabase(connection)
        finally:
            connection.close()
    elif access == "orm":
        with TestingSessionLocal() as session:
            yield OrmDatabase(session)
    else:
        raise ValueError(f"unknown database access {access!r}")


@contextmanager
def fresh_database(access):
    """A Database on a freshly created, empty schema, dropped again afterwards."""
    if access == "sql":
        require_postgres()
        with connect(TEST_DATABASE_URL) as connection:
            create_schema(connection)
            connection.commit()
    else:
        Base.metadata.create_all(engine)
    try:
        with open_database(access) as database:
            yield database
    finally:
        if access == "sql":
            with connect(TEST_DATABASE_URL) as connection:
                drop_schema(connection)
                connection.commit()
        else:
            Base.metadata.drop_all(engine)


# Which storage backend the API tests use: "local" (default) or "s3" (a moto-mocked bucket).
# CI runs the suite with both.
TEST_STORAGE_BACKEND = os.getenv("TEST_STORAGE_BACKEND", "local")
TEST_BUCKET = "test-project-documents"
TEST_REGION = "eu-north-1"


@pytest.fixture
def db():
    """The test database with a fresh, empty schema, as a Database for setting up and checking data.

    It goes through the same interface as the app, so tests don't depend on how the app accesses the
    database. API requests each get their own Database on the same database, as in production.
    TEST_DATABASE_ACCESS decides the backend.
    """
    with fresh_database(TEST_DATABASE_ACCESS) as database:
        yield database


@pytest.fixture(params=["orm", "sql"])
def any_db(request):
    """Like `db`, for each backend in turn; tests using it run once per backend."""
    with fresh_database(request.param) as database:
        yield database


@pytest.fixture
def run_sql(db):
    """Runs a SQL statement (with :named parameters) and commits it.

    For setting up state the app can't produce through its interface, e.g. data from before a migration.
    """

    def _run_sql(statement, **params):
        with engine.begin() as connection:
            connection.execute(text(statement), params)

    return _run_sql


@pytest.fixture
def count_rows(db):
    """Returns the number of rows in a table."""

    def _count_rows(table):
        with engine.connect() as connection:
            return connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()

    return _count_rows


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
def client(db, storage, mailer):
    """API client whose requests use the test database, storage and mailer."""

    def override_get_db():
        with open_database(TEST_DATABASE_ACCESS) as database:
            yield database

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_mailer] = lambda: mailer
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
