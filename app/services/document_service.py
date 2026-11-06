from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import MAX_DOCUMENT_SIZE
from app.models.document import Document
from app.models.project_user import ProjectRole
from app.models.user import User
from app.repositories import document_repository, project_repository
from app.storage import Storage, StoredFileNotFoundError


class DocumentNotFoundError(Exception):
    """The document doesn't exist, or the user has no access to its project (not distinguished)."""


class NotProjectOwnerError(Exception):
    """The user is a member of the document's project, but only its owner may do this."""


class DocumentFileMissingError(Exception):
    """The document exists, but its file is missing from storage."""


class UnsupportedDocumentTypeError(Exception):
    """The file is not one of the accepted document types."""


class DocumentTooLargeError(Exception):
    """The file is larger than MAX_DOCUMENT_SIZE."""


class EmptyDocumentError(Exception):
    """The file has no content."""


# TASK.md: projects hold docx and pdf documents. The content type is derived from the
# extension rather than taken from the client.
ALLOWED_DOCUMENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def validate_file(filename: str | None, data: bytes) -> tuple[str, str]:
    """Check an uploaded file; returns its cleaned filename and content type."""
    # Browsers may send a full client-side path; keep only the last part.
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()[:255]
    extension = name[name.rfind("."):].lower() if "." in name else ""
    if extension not in ALLOWED_DOCUMENT_TYPES:
        raise UnsupportedDocumentTypeError(name)
    if len(data) > MAX_DOCUMENT_SIZE:
        raise DocumentTooLargeError(name)
    if not data:
        raise EmptyDocumentError(name)
    return name, ALLOWED_DOCUMENT_TYPES[extension]


def _new_storage_key(project_id: int) -> str:
    return f"projects/{project_id}/documents/{uuid4().hex}"


def get_document(session: Session, user: User, document_id: int) -> Document:
    """The document, if `user` is the owner or a participant of its project."""
    document = document_repository.get(session, document_id)
    if document is None or project_repository.get_membership(session, document.project_id, user.id) is None:
        raise DocumentNotFoundError(document_id)
    return document


def download_document(session: Session, storage: Storage, user: User, document_id: int) -> tuple[Document, bytes]:
    """The document and its file contents."""
    document = get_document(session, user, document_id)
    try:
        return document, storage.load(document.storage_key)
    except StoredFileNotFoundError:
        raise DocumentFileMissingError(document_id) from None


def replace_document(
    session: Session, storage: Storage, user: User, document_id: int, filename: str | None, data: bytes
) -> Document:
    """Replace the document's file (owner or participant); returns the updated document."""
    document = get_document(session, user, document_id)
    name, content_type = validate_file(filename, data)

    # Store the new file under a fresh key and only drop the old one once the database
    # points at the new file, so a failure never leaves the document without a file.
    old_key, new_key = document.storage_key, _new_storage_key(document.project_id)
    storage.save(new_key, data)
    try:
        document = document_repository.update(session, document, new_key, name, content_type)
    except Exception:
        session.rollback()
        storage.delete(new_key)
        raise
    storage.delete(old_key)
    return document


def delete_document(session: Session, storage: Storage, user: User, document_id: int) -> None:
    """Delete the document and its file; only the project's owner may do this
    (TASK.md: participants can modify, but not delete)."""
    document = document_repository.get(session, document_id)
    membership = (
        None if document is None
        else project_repository.get_membership(session, document.project_id, user.id)
    )
    if membership is None:
        raise DocumentNotFoundError(document_id)
    if membership.role != ProjectRole.OWNER:
        raise NotProjectOwnerError(document_id)

    storage_key = document.storage_key
    document_repository.delete(session, document)
    # Removed after the commit: a failure here leaves an orphaned file, never a document without one.
    storage.delete(storage_key)
