from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.user import User
from app.repositories import project_repository
from app.schemas.project_schema import ProjectCreate


def create_project(session: Session, user: User, project_create: ProjectCreate) -> Project:
    """Create a project with `user` as its owner."""
    return project_repository.create_project(
        session,
        name=project_create.name,
        description=project_create.description,
        owner=user,
    )


def list_projects(session: Session, user: User) -> list[Project]:
    """All projects `user` can access."""
    return project_repository.list_for_user(session, user.id)
