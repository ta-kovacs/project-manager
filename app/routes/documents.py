from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.config import MAX_DOCUMENT_SIZE, PROJECT_STORAGE_LIMIT
from app.db.engine import get_db
from app.db.interface import Database
from app.db.records import User
from app.dependencies import get_current_user
from app.schemas.project_schema import DocumentRead
from app.services import document_service, project_service
from app.storage import Storage, get_storage

router = APIRouter(
    tags=["documents"],
    responses={401: {"description": "Missing or invalid credentials"}},
)

_NOT_FOUND = {404: {"description": "Document doesn't exist or the caller has no access to its project"}}
_PROJECT_NOT_FOUND = {404: {"description": "Project doesn't exist or the caller has no access"}}


def _document_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")


def _project_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")


def _invalid_file(error: document_service.InvalidDocumentError, *, name_file: bool = False) -> HTTPException:
    """The HTTP error for a rejected upload; `name_file` adds the file's name (for multi-file uploads)."""
    if isinstance(error, document_service.UnsupportedDocumentTypeError):
        code, detail = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF and DOCX documents are accepted"
    elif isinstance(error, document_service.DocumentTooLargeError):
        code, detail = status.HTTP_413_CONTENT_TOO_LARGE, f"Documents can be at most {MAX_DOCUMENT_SIZE} bytes"
    else:
        code, detail = status.HTTP_422_UNPROCESSABLE_CONTENT, "File is empty"
    if name_file:
        detail = f"{detail}: {error.filename or '(no filename)'}"
    return HTTPException(code, detail=detail)


def _read_upload(file: UploadFile) -> bytes:
    return file.file.read(MAX_DOCUMENT_SIZE + 1)  # one byte over the limit is enough to reject it


def _storage_limit_reached() -> HTTPException:
    return HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE,
        detail=f"The project's documents can take up at most {PROJECT_STORAGE_LIMIT} bytes in total",
    )


_UPLOAD_ERRORS = {
    413: {"description": "A file is larger than the allowed size, or the project's storage limit would be exceeded"},
    415: {"description": "A file is not a PDF or DOCX document"},
}


def _attachment(filename: str) -> str:
    """Content-Disposition value that keeps non-ASCII filenames intact (RFC 6266 / 5987)."""
    ascii_fallback = filename.encode("ascii", "replace").decode().replace('"', "")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.get(
    "/project/{project_id}/documents",
    response_model=list[DocumentRead],
    responses=_PROJECT_NOT_FOUND,
)
def list_project_documents(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """All of a project's documents, if the caller is its owner or a participant."""
    try:
        return document_service.list_project_documents(db, user, project_id)
    except project_service.ProjectNotFoundError:
        raise _project_not_found() from None


@router.post(
    "/project/{project_id}/documents",
    response_model=list[DocumentRead],
    status_code=status.HTTP_201_CREATED,
    responses={**_UPLOAD_ERRORS, **_PROJECT_NOT_FOUND},
)
def upload_documents(
    project_id: int,
    files: list[UploadFile] = File(description="One or more PDF or DOCX files"),
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    """Upload documents to a project (owner or participant); returns the created documents.

    One invalid file rejects the whole upload; the error names that file.
    """
    uploads = [(file.filename, _read_upload(file)) for file in files]
    try:
        return document_service.upload_documents(db, storage, user, project_id, uploads)
    except project_service.ProjectNotFoundError:
        raise _project_not_found() from None
    except document_service.TooManyFilesError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"At most {document_service.MAX_FILES_PER_UPLOAD} files can be uploaded at once",
        ) from None
    except document_service.InvalidDocumentError as error:
        raise _invalid_file(error, name_file=True) from error
    except document_service.ProjectStorageLimitError:
        raise _storage_limit_reached() from None


@router.get(
    "/document/{document_id}",
    response_class=Response,
    responses={200: {"description": "The document's file", "content": {"application/octet-stream": {}}}, **_NOT_FOUND},
)
def download_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    """Download a document's file, if the caller is the owner or a participant of its project."""
    try:
        document, data = document_service.download_document(db, storage, user, document_id)
    except document_service.DocumentNotFoundError:
        raise _document_not_found() from None
    except document_service.DocumentFileMissingError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document file not found") from None

    return Response(
        content=data,
        media_type=document.content_type,
        headers={"Content-Disposition": _attachment(document.original_filename)},
    )


@router.put(
    "/document/{document_id}",
    response_model=DocumentRead,
    responses={**_UPLOAD_ERRORS, **_NOT_FOUND},
)
def replace_document(
    document_id: int,
    file: UploadFile = File(description="The new PDF or DOCX file"),
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    """Replace a document's file (owner or participant); returns the updated document."""
    try:
        return document_service.replace_document(db, storage, user, document_id, file.filename, _read_upload(file))
    except document_service.DocumentNotFoundError:
        raise _document_not_found() from None
    except document_service.InvalidDocumentError as error:
        raise _invalid_file(error) from error
    except document_service.ProjectStorageLimitError:
        raise _storage_limit_reached() from None


@router.delete(
    "/document/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={403: {"description": "Only the project's owner can delete documents"}, **_NOT_FOUND},
)
def delete_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    """Delete a document and remove it from its project (project owner only)."""
    try:
        document_service.delete_document(db, storage, user, document_id)
    except document_service.DocumentNotFoundError:
        raise _document_not_found() from None
    except document_service.NotProjectOwnerError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the project owner can delete documents") from None
