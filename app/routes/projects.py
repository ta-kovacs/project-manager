from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.project_schema import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import project_service

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
        raise _project_not_found()


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
        raise _project_not_found()
