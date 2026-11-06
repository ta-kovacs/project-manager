"""Where document files are kept.

Deployed environments use S3 (TASK.md: AWS S3 file storage); local disk is for development and
tests. Routes only depend on `get_storage`, so they work the same with either backend.
"""
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import boto3
from botocore.exceptions import ClientError

from app.config import S3_BUCKET, STORAGE_BACKEND, STORAGE_DIR


class StoredFileNotFoundError(Exception):
    """No file is stored under the given key."""


class Storage(Protocol):
    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...

    def load(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None:
        """Remove the file; deleting a key that holds no file is not an error."""
        ...


class LocalStorage:
    """Stores each file at `<root>/<key>` on the local filesystem."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"storage key escapes the storage root: {key!r}")
        return path

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def load(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise StoredFileNotFoundError(key) from None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    """Stores each file as the object `<key>` in an S3 bucket."""

    def __init__(self, bucket: str, client=None):
        self.bucket = bucket
        self.client = client or boto3.client("s3")

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        # The content type is kept on the object, so it is right when viewed in the console or
        # served directly (e.g. via presigned URLs), and available to Lambda functions.
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def load(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise StoredFileNotFoundError(key) from None
            raise
        return response["Body"].read()

    def delete(self, key: str) -> None:
        # S3 treats deleting a missing key as a success.
        self.client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache
def get_storage() -> Storage:
    """The configured storage backend (created once and reused)."""
    if STORAGE_BACKEND == "s3":
        if not S3_BUCKET:
            raise RuntimeError("STORAGE_BACKEND is 's3' but S3_BUCKET is not set")
        return S3Storage(S3_BUCKET)
    if STORAGE_BACKEND == "local":
        return LocalStorage(STORAGE_DIR)
    raise RuntimeError(f"Unknown STORAGE_BACKEND {STORAGE_BACKEND!r} (expected 's3' or 'local')")
