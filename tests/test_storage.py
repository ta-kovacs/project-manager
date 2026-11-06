"""LocalStorage: document files on the local filesystem."""
import pytest

from app.storage import StoredFileNotFoundError


def test_save_then_load_returns_same_bytes(storage):
    storage.save("projects/1/documents/abc", b"%PDF-1.4 content")

    assert storage.load("projects/1/documents/abc") == b"%PDF-1.4 content"


def test_save_creates_file_under_root(storage):
    storage.save("projects/1/documents/abc", b"data")

    assert (storage.root / "projects" / "1" / "documents" / "abc").read_bytes() == b"data"


def test_save_overwrites_existing_file(storage):
    storage.save("key", b"old")
    storage.save("key", b"new")

    assert storage.load("key") == b"new"


def test_load_missing_key_raises(storage):
    with pytest.raises(StoredFileNotFoundError):
        storage.load("does/not/exist")


def test_delete_removes_file(storage):
    storage.save("key", b"data")

    storage.delete("key")

    with pytest.raises(StoredFileNotFoundError):
        storage.load("key")


def test_delete_missing_key_is_not_an_error(storage):
    storage.delete("does/not/exist")


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("../outside", id="parent-directory"),
        pytest.param("projects/../../outside", id="nested-parent-directory"),
        pytest.param("/etc/passwd", id="absolute-path"),
    ],
)
@pytest.mark.parametrize("operation", ["save", "load", "delete"])
def test_keys_escaping_root_are_rejected(storage, operation, key):
    args = (key, b"data") if operation == "save" else (key,)

    with pytest.raises(ValueError, match="escapes the storage root"):
        getattr(storage, operation)(*args)
