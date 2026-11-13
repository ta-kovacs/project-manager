"""The data the database layer hands to the rest of the app.

Both backends (app/db/orm, app/db/sql) return these plain, immutable records, so services, routes and
response schemas never depend on how the data was loaded. A record is a snapshot: to change data, call a
repository method, which returns a new record.
"""

import enum
from dataclasses import dataclass
from datetime import datetime


class ProjectRole(enum.StrEnum):
    OWNER = "owner"
    PARTICIPANT = "participant"


@dataclass(frozen=True)
class User:
    id: int
    username: str
    # Argon2 hash from app.security; the plain password is never stored
    password_hash: str


@dataclass(frozen=True)
class Document:
    id: int
    project_id: int
    storage_key: str
    original_filename: str
    content_type: str
    # NULL for documents uploaded before sizes were recorded
    size_bytes: int | None


@dataclass(frozen=True)
class NewDocument:
    """A document to be created (it has no id yet)."""

    storage_key: str
    original_filename: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True)
class Project:
    """A project with everything GET /project/{id}/info returns: details, owner and documents."""

    id: int
    name: str
    description: str | None
    storage_used_bytes: int
    storage_measured_at: datetime | None
    owner: User
    # oldest first
    documents: tuple[Document, ...]


@dataclass(frozen=True)
class Membership:
    """A user's access to a project."""

    project_id: int
    user: User
    role: ProjectRole
