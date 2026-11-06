from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
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
