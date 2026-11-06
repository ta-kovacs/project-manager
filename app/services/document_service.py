from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User
from app.repositories import document_repository, project_repository
from app.storage import Storage, StoredFileNotFoundError


class DocumentNotFoundError(Exception):
    """The document doesn't exist, or the user has no access to its project (not distinguished)."""


class DocumentFileMissingError(Exception):
    """The document exists, but its file is missing from storage."""


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
