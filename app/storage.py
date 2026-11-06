"""Where document files are kept. Routes depend on `get_storage`, so the backend can change (e.g. S3)."""
from pathlib import Path
from typing import Protocol

from app.config import STORAGE_DIR


class StoredFileNotFoundError(Exception):
    """No file is stored under the given key."""


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...

    def load(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalStorage:
    """Stores each file at `<root>/<key>` on the local filesystem."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"storage key escapes the storage root: {key!r}")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def load(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise StoredFileNotFoundError(key) from None

    def delete(self, key: str) -> None:
        """Remove the file; deleting a key that holds no file is not an error."""
        self._path(key).unlink(missing_ok=True)


def get_storage() -> Storage:
    # TODO: switch to an S3-backed Storage for deployments (TASK.md: AWS S3 file storage)
    return LocalStorage(STORAGE_DIR)
