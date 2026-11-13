from uuid import uuid4

from app.config import MAX_DOCUMENT_SIZE, PROJECT_STORAGE_LIMIT
from app.db.interface import Database
from app.db.records import Document, NewDocument, ProjectRole, User
from app.services import project_service
from app.storage import Storage, StoredFileNotFoundError


class DocumentNotFoundError(Exception):
    """The document doesn't exist, or the user has no access to its project (not distinguished)."""


class NotProjectOwnerError(Exception):
    """The user is a member of the document's project, but only its owner may do this."""


class DocumentFileMissingError(Exception):
    """The document exists, but its file is missing from storage."""


class InvalidDocumentError(Exception):
    """An uploaded file was rejected; `filename` is the (cleaned) name of that file."""

    def __init__(self, filename: str):
        super().__init__(filename)
        self.filename = filename


class UnsupportedDocumentTypeError(InvalidDocumentError):
    """The file is not one of the accepted document types."""


class DocumentTooLargeError(InvalidDocumentError):
    """The file is larger than MAX_DOCUMENT_SIZE."""


class EmptyDocumentError(InvalidDocumentError):
    """The file has no content."""


class TooManyFilesError(Exception):
    """More files were uploaded at once than MAX_FILES_PER_UPLOAD."""


class ProjectStorageLimitError(Exception):
    """Storing the upload would take the project over PROJECT_STORAGE_LIMIT."""


MAX_FILES_PER_UPLOAD = 10


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
    extension = name[name.rfind(".") :].lower() if "." in name else ""
    if extension not in ALLOWED_DOCUMENT_TYPES:
        raise UnsupportedDocumentTypeError(name)
    if len(data) > MAX_DOCUMENT_SIZE:
        raise DocumentTooLargeError(name)
    if not data:
        raise EmptyDocumentError(name)
    return name, ALLOWED_DOCUMENT_TYPES[extension]


def _new_storage_key(project_id: int) -> str:
    return f"projects/{project_id}/documents/{uuid4().hex}"


def get_document(db: Database, user: User, document_id: int) -> Document:
    """The document, if `user` is the owner or a participant of its project."""
    document = db.documents.get(document_id)
    if document is None or db.projects.get_membership(document.project_id, user.id) is None:
        raise DocumentNotFoundError(document_id)
    return document


def list_project_documents(db: Database, user: User, project_id: int) -> list[Document]:
    """The project's documents, if `user` is its owner or a participant.

    Raises project_service.ProjectNotFoundError otherwise.
    """
    project = project_service.get_project(db, user, project_id)
    return db.documents.list_for_project(project.id)


def upload_documents(
    db: Database, storage: Storage, user: User, project_id: int, files: list[tuple[str | None, bytes]]
) -> list[Document]:
    """Add `files` (filename, contents) to the project as new documents (owner or participant).

    All files are validated before anything is stored: one invalid file rejects the whole upload, and so
    does going over the project's storage limit.
    """
    project = project_service.get_project(db, user, project_id)
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise TooManyFilesError(len(files))
    checked = [(*validate_file(filename, data), data) for filename, data in files]
    upload_size = sum(len(data) for _, _, data in checked)

    stored: list[NewDocument] = []
    try:
        # Reserved in the same transaction that creates the documents, so a failed upload releases it.
        if not db.projects.adjust_storage_used(project.id, upload_size, limit=PROJECT_STORAGE_LIMIT):
            raise ProjectStorageLimitError(project.id)
        for name, content_type, data in checked:
            key = _new_storage_key(project.id)
            storage.save(key, data, content_type)
            stored.append(NewDocument(key, name, content_type, len(data)))
        documents = db.documents.create_many(project.id, stored)
        db.commit()
    except Exception:
        # Don't leave files behind for documents that were never created.
        db.rollback()
        for new in stored:
            storage.delete(new.storage_key)
        raise
    return documents


def download_document(db: Database, storage: Storage, user: User, document_id: int) -> tuple[Document, bytes]:
    """The document and its file contents."""
    document = get_document(db, user, document_id)
    try:
        return document, storage.load(document.storage_key)
    except StoredFileNotFoundError:
        raise DocumentFileMissingError(document_id) from None


def replace_document(
    db: Database, storage: Storage, user: User, document_id: int, filename: str | None, data: bytes
) -> Document:
    """Replace the document's file (owner or participant); returns the updated document."""
    document = get_document(db, user, document_id)
    name, content_type = validate_file(filename, data)

    # Only growing a document is checked against the limit; a document of unknown size (uploaded before
    # sizes were recorded) counts as growing by its full new size until the Lambda corrects the total.
    growth = len(data) - (document.size_bytes or 0)
    limit = PROJECT_STORAGE_LIMIT if growth > 0 else None
    if not db.projects.adjust_storage_used(document.project_id, growth, limit=limit):
        db.rollback()
        raise ProjectStorageLimitError(document.project_id)

    # Store the new file under a fresh key and only drop the old one once the database
    # points at the new file, so a failure never leaves the document without a file.
    old_key, new_key = document.storage_key, _new_storage_key(document.project_id)
    try:
        storage.save(new_key, data, content_type)
        updated = db.documents.update(document.id, new_key, name, content_type, len(data))
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(new_key)
        raise
    storage.delete(old_key)
    return updated


def delete_document(db: Database, storage: Storage, user: User, document_id: int) -> None:
    """Delete the document and its file; only the project's owner may do this
    (TASK.md: participants can modify, but not delete)."""
    document = db.documents.get(document_id)
    membership = None if document is None else db.projects.get_membership(document.project_id, user.id)
    if membership is None:
        raise DocumentNotFoundError(document_id)
    if membership.role != ProjectRole.OWNER:
        raise NotProjectOwnerError(document_id)

    db.projects.adjust_storage_used(document.project_id, -(document.size_bytes or 0))
    db.documents.delete(document.id)
    db.commit()
    # Removed after the commit: a failure here leaves an orphaned file, never a document without one.
    storage.delete(document.storage_key)
