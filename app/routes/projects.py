from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import EmailStr
from sqlalchemy.orm import Session

from app.config import PUBLIC_BASE_URL, SHARE_LINK_MAX_AGE
from app.database import get_db
from app.dependencies import get_current_user
from app.mailer import MailDeliveryError, Mailer, get_mailer
from app.models.user import User
from app.schemas.project_schema import MemberRead, ProjectCreate, ProjectRead, ProjectUpdate, ShareRead
from app.security import ExpiredShareTokenError, InvalidShareTokenError
from app.services import project_service
from app.storage import Storage, get_storage

router = APIRouter(
    tags=["projects"],
    responses={401: {"description": "Missing or invalid credentials"}},
)


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    project_create: ProjectCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    """Create a project; the caller becomes its owner."""
    return project_service.create_project(session, user, project_create)


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    """All projects the caller owns or participates in, with their full info."""
    return project_service.list_projects(session, user)


def _project_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get(
    "/project/{project_id}/info",
    response_model=ProjectRead,
    responses={404: {"description": "Project doesn't exist or the caller has no access"}},
)
def get_project_info(
    project_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    """A project's full info, if the caller is its owner or a participant."""
    try:
        return project_service.get_project(session, user, project_id)
    except project_service.ProjectNotFoundError:
        raise _project_not_found() from None


@router.put(
    "/project/{project_id}/info",
    response_model=ProjectRead,
    responses={404: {"description": "Project doesn't exist or the caller has no access"}},
)
def update_project_info(
    project_id: int,
    project_update: ProjectUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    """Replace a project's name and description (owner or participant); returns the updated info."""
    try:
        return project_service.update_project(session, user, project_id, project_update)
    except project_service.ProjectNotFoundError:
        raise _project_not_found() from None


@router.delete(
    "/project/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"description": "Only the project's owner can delete it"},
        404: {"description": "Project doesn't exist or the caller has no access"},
    },
)
def delete_project(
    project_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    """Delete a project and its documents, including their stored files (owner only)."""
    try:
        project_service.delete_project(session, storage, user, project_id)
    except project_service.ProjectNotFoundError:
        raise _project_not_found() from None
    except project_service.NotProjectOwnerError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the project owner can delete it") from None


@router.post(
    "/project/{project_id}/invite",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "Only the project's owner can invite users"},
        404: {"description": "Project or user doesn't exist, or the caller has no access to the project"},
        409: {"description": "The user already has access to the project"},
    },
)
def invite_user(
    project_id: int,
    username: str = Query(alias="user", min_length=1, description="Login of the user to invite"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    """Grant a user participant access to a project (owner only)."""
    try:
        return project_service.invite_user(session, user, project_id, username)
    except project_service.ProjectNotFoundError:
        raise _project_not_found() from None
    except project_service.NotProjectOwnerError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the project owner can invite users") from None
    except project_service.UserNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found") from None
    except project_service.AlreadyMemberError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="User already has access to the project") from None


@router.get(
    "/project/{project_id}/share",
    response_model=ShareRead,
    responses={
        403: {"description": "Only the project's owner can share it"},
        404: {"description": "Project doesn't exist or the caller has no access"},
        502: {"description": "The email could not be sent"},
    },
)
def share_project(
    project_id: int,
    request: Request,
    email: EmailStr = Query(alias="with", description="Email address to send the join link to"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    mailer: Mailer = Depends(get_mailer),
):
    """Email a GET /join link that gives whoever opens it participant access (owner only)."""
    base_url = (PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")

    def join_url(token: str) -> str:
        return f"{base_url}/join?token={token}"

    try:
        project_service.share_project(session, mailer, user, project_id, email, join_url)
    except project_service.ProjectNotFoundError:
        raise _project_not_found() from None
    except project_service.NotProjectOwnerError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the project owner can share it") from None
    except MailDeliveryError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="The email could not be sent") from None
    return ShareRead(project_id=project_id, email=email, expires_in=SHARE_LINK_MAX_AGE)


@router.get(
    "/join",
    response_model=MemberRead,
    responses={
        400: {"description": "The share link is invalid"},
        404: {"description": "The shared project no longer exists"},
        410: {"description": "The share link has expired"},
    },
)
def join_project(
    token: str = Query(description="Token from a share link (GET /project/{id}/share)"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    """Join a project through a share link: the signed-in caller becomes a participant.

    Like every protected endpoint it needs the caller's access token (`Authorization: Bearer`), so a
    client opening the link must sign in through POST /login first. Joining a project the caller already has access to returns their existing membership.
    """
    try:
        return project_service.join_project(session, user, token)
    except InvalidShareTokenError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid share link") from None
    except ExpiredShareTokenError:
        raise HTTPException(status.HTTP_410_GONE, detail="This share link has expired") from None
    except project_service.ProjectNotFoundError:
        raise _project_not_found() from None
