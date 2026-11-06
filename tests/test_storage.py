"""Document file storage: behaviour shared by both backends, then backend-specific details."""
import pytest
from botocore.exceptions import ClientError

import app.storage as storage_module
from app.storage import LocalStorage, S3Storage, StoredFileNotFoundError


# --- both backends (`any_storage` runs each test for local disk and for mocked S3) ---------------

def test_save_then_load_returns_same_bytes(any_storage):
    any_storage.save("projects/1/documents/abc", b"%PDF-1.4 content", "application/pdf")

    assert any_storage.load("projects/1/documents/abc") == b"%PDF-1.4 content"


def test_save_overwrites_existing_file(any_storage):
    any_storage.save("key", b"old")
    any_storage.save("key", b"new")

    assert any_storage.load("key") == b"new"


def test_load_missing_key_raises(any_storage):
    with pytest.raises(StoredFileNotFoundError):
        any_storage.load("does/not/exist")


def test_delete_removes_file(any_storage):
    any_storage.save("key", b"data")

    any_storage.delete("key")

    with pytest.raises(StoredFileNotFoundError):
        any_storage.load("key")


def test_delete_missing_key_is_not_an_error(any_storage):
    any_storage.delete("does/not/exist")


def test_files_are_kept_apart_by_key(any_storage):
    any_storage.save("projects/1/documents/a", b"first")
    any_storage.save("projects/2/documents/a", b"second")

    any_storage.delete("projects/1/documents/a")

    assert any_storage.load("projects/2/documents/a") == b"second"


# --- local disk -----------------------------------------------------------------------------------

@pytest.fixture
def local_storage(tmp_path):
    return LocalStorage(tmp_path / "storage")


def test_local_save_creates_file_under_root(local_storage):
    local_storage.save("projects/1/documents/abc", b"data")

    assert (local_storage.root / "projects" / "1" / "documents" / "abc").read_bytes() == b"data"


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("../outside", id="parent-directory"),
        pytest.param("projects/../../outside", id="nested-parent-directory"),
        pytest.param("/etc/passwd", id="absolute-path"),
    ],
)
@pytest.mark.parametrize("operation", ["save", "load", "delete"])
def test_local_keys_escaping_root_are_rejected(local_storage, operation, key):
    args = (key, b"data") if operation == "save" else (key,)

    with pytest.raises(ValueError, match="escapes the storage root"):
        getattr(local_storage, operation)(*args)


# --- S3 -------------------------------------------------------------------------------------------

@pytest.fixture
def s3_storage(s3_client, s3_bucket):
    return S3Storage(s3_bucket, client=s3_client)


def test_s3_save_stores_object_with_content_type(s3_storage, s3_client, s3_bucket):
    s3_storage.save("projects/1/documents/abc", b"%PDF", "application/pdf")

    head = s3_client.head_object(Bucket=s3_bucket, Key="projects/1/documents/abc")
    assert head["ContentType"] == "application/pdf"
    assert head["ContentLength"] == 4


def test_s3_save_without_content_type_uses_octet_stream(s3_storage, s3_client, s3_bucket):
    s3_storage.save("key", b"data")

    assert s3_client.head_object(Bucket=s3_bucket, Key="key")["ContentType"] == "application/octet-stream"


def test_s3_errors_other_than_missing_key_are_raised(s3_client):
    # e.g. a misconfigured bucket name must not look like "document file not found"
    storage = S3Storage("bucket-that-does-not-exist", client=s3_client)

    with pytest.raises(ClientError) as error:
        storage.load("key")

    assert error.value.response["Error"]["Code"] == "NoSuchBucket"


# --- choosing the backend (get_storage) -----------------------------------------------------------

@pytest.fixture
def configure_storage(monkeypatch, tmp_path):
    """Set the storage settings get_storage reads, with a fresh cache before and after."""
    def _configure(backend, bucket=None):
        monkeypatch.setattr(storage_module, "STORAGE_BACKEND", backend)
        monkeypatch.setattr(storage_module, "S3_BUCKET", bucket)
        monkeypatch.setattr(storage_module, "STORAGE_DIR", str(tmp_path / "storage"))
        storage_module.get_storage.cache_clear()

    yield _configure
    storage_module.get_storage.cache_clear()


def test_get_storage_local(configure_storage, tmp_path):
    configure_storage("local")

    storage = storage_module.get_storage()

    assert isinstance(storage, LocalStorage)
    assert storage.root == (tmp_path / "storage").resolve()


def test_get_storage_s3(configure_storage, s3_client, s3_bucket):
    configure_storage("s3", bucket=s3_bucket)

    storage = storage_module.get_storage()

    assert isinstance(storage, S3Storage)
    assert storage.bucket == s3_bucket


def test_get_storage_is_reused(configure_storage):
    configure_storage("local")

    assert storage_module.get_storage() is storage_module.get_storage()


@pytest.mark.parametrize(
    ("backend", "bucket", "message"),
    [
        pytest.param("s3", None, "S3_BUCKET is not set", id="s3-without-bucket"),
        pytest.param("ftp", None, "Unknown STORAGE_BACKEND 'ftp'", id="unknown-backend"),
    ],
)
def test_get_storage_misconfiguration_fails(configure_storage, backend, bucket, message):
    configure_storage(backend, bucket=bucket)

    with pytest.raises(RuntimeError, match=message):
        storage_module.get_storage()
