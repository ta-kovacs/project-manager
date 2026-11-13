"""What every database backend provides.

The services only use these protocols. app/db/orm implements them with SQLAlchemy ORM models, app/db/sql
with hand-written SQL; DATABASE_ACCESS (app/config.py) picks one.

Conventions shared by both backends:

- Repositories never commit. A service makes its changes and then calls `Database.commit()`, or
  `Database.rollback()` to undo them, so several changes succeed or fail together.
- Reads return the current state of the database (never a cached copy) as records from app.db.records.
- A write that breaks a uniqueness rule raises ConflictError; the transaction must then be rolled back.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.db.records import Document, Membership, NewDocument, Project, ProjectRole, User


class ConflictError(Exception):
    """A write broke a uniqueness rule (e.g. a username or membership that already exists)."""


class UserRepository(Protocol):
    def get_by_id(self, user_id: int) -> User | None: ...

    def get_by_username(self, username: str) -> User | None: ...

    def create(self, username: str, password_hash: str) -> User:
        """Raises ConflictError if the username is taken."""
        ...


class ProjectRepository(Protocol):
    def get(self, project_id: int) -> Project | None: ...

    def list_for_user(self, user_id: int) -> list[Project]:
        """Projects the user is a member of (owner or participant), oldest first."""
        ...

    def create(self, name: str, description: str | None, owner_id: int) -> Project:
        """A new project with `owner_id` as its owner."""
        ...

    def update(self, project_id: int, name: str, description: str | None) -> Project: ...

    def delete(self, project_id: int) -> None:
        """Delete the project with its memberships and document records (not their stored files)."""
        ...

    def get_membership(self, project_id: int, user_id: int) -> Membership | None: ...

    def add_member(self, project_id: int, user_id: int, role: ProjectRole) -> Membership:
        """Raises ConflictError if the user already is a member, or if a second owner is added."""
        ...

    def adjust_storage_used(self, project_id: int, delta: int, *, limit: int | None = None) -> bool:
        """Add `delta` bytes (negative to release them) to the project's storage counter.

        With `limit`, the change is only made if the counter stays within it; returns whether it was made.
        The check and the change are one UPDATE, so concurrent uploads can't both slip under the limit.
        The counter never goes below zero.
        """
        ...

    def record_measured_storage(self, project_id: int, total_size_bytes: int, measured_at: datetime) -> bool:
        """Set the storage counter to a measured total unless a newer measurement is stored.

        Returns whether it was stored (False also when the project doesn't exist).
        """
        ...


class DocumentRepository(Protocol):
    def get(self, document_id: int) -> Document | None: ...

    def list_for_project(self, project_id: int) -> list[Document]:
        """The project's documents, oldest first."""
        ...

    def create_many(self, project_id: int, documents: Sequence[NewDocument]) -> list[Document]: ...

    def update(
        self, document_id: int, storage_key: str, original_filename: str, content_type: str, size_bytes: int
    ) -> Document: ...

    def delete(self, document_id: int) -> None: ...


class Database(Protocol):
    """One unit of work: repositories sharing a transaction."""

    users: UserRepository
    projects: ProjectRepository
    documents: DocumentRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
