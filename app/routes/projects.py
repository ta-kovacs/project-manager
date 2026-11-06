from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.project_schema import ProjectCreate, ProjectRead
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
