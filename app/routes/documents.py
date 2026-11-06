from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.config import MAX_DOCUMENT_SIZE
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.project_schema import DocumentRead
from app.services import document_service
from app.storage import Storage, get_storage

router = APIRouter(
    tags=["documents"],
    responses={401: {"description": "Missing or invalid credentials"}},
)

_NOT_FOUND = {404: {"description": "Document doesn't exist or the caller has no access to its project"}}


def _document_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")


def _attachment(filename: str) -> str:
    """Content-Disposition value that keeps non-ASCII filenames intact (RFC 6266 / 5987)."""
    ascii_fallback = filename.encode("ascii", "replace").decode().replace('"', "")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.get(
    "/document/{document_id}",
    response_class=Response,
    responses={200: {"description": "The document's file", "content": {"application/octet-stream": {}}}, **_NOT_FOUND},
)
def download_document(
    document_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    """Download a document's file, if the caller is the owner or a participant of its project."""
    try:
        document, data = document_service.download_document(session, storage, user, document_id)
    except document_service.DocumentNotFoundError:
        raise _document_not_found()
    except document_service.DocumentFileMissingError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document file not found")

    return Response(
        content=data,
        media_type=document.content_type,
        headers={"Content-Disposition": _attachment(document.original_filename)},
    )


@router.put(
    "/document/{document_id}",
    response_model=DocumentRead,
    responses={
        413: {"description": "File is larger than the allowed size"},
        415: {"description": "File is not a PDF or DOCX document"},
        **_NOT_FOUND,
    },
)
def replace_document(
    document_id: int,
    file: UploadFile = File(description="The new PDF or DOCX file"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    """Replace a document's file (owner or participant); returns the updated document."""
    data = file.file.read(MAX_DOCUMENT_SIZE + 1)  # one byte over the limit is enough to reject it
    try:
        return document_service.replace_document(session, storage, user, document_id, file.filename, data)
    except document_service.DocumentNotFoundError:
        raise _document_not_found()
    except document_service.UnsupportedDocumentTypeError:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only PDF and DOCX documents are accepted"
        )
    except document_service.DocumentTooLargeError:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Documents can be at most {MAX_DOCUMENT_SIZE} bytes",
        )
    except document_service.EmptyDocumentError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="File is empty")


@router.delete(
    "/document/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={403: {"description": "Only the project's owner can delete documents"}, **_NOT_FOUND},
)
def delete_document(
    document_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    """Delete a document and remove it from its project (project owner only)."""
    try:
        document_service.delete_document(session, storage, user, document_id)
    except document_service.DocumentNotFoundError:
        raise _document_not_found()
    except document_service.NotProjectOwnerError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the project owner can delete documents")
