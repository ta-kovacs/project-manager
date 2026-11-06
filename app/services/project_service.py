from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_user import ProjectRole, ProjectUser
from app.models.user import User
from app.repositories import project_repository
from app.schemas.project_schema import ProjectCreate, ProjectUpdate
from app.storage import Storage


class ProjectNotFoundError(Exception):
    """The project doesn't exist, or the user isn't a member (the two aren't distinguished)."""


class NotProjectOwnerError(Exception):
    """The user is a member of the project, but the action is reserved for its owner."""


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


def _get_membership(session: Session, user: User, project_id: int) -> ProjectUser:
    membership = project_repository.get_membership(session, project_id, user.id)
    if membership is None:
        raise ProjectNotFoundError(project_id)
    return membership


def get_project(session: Session, user: User, project_id: int) -> Project:
    """The project, if `user` is its owner or a participant."""
    return _get_membership(session, user, project_id).project


def update_project(session: Session, user: User, project_id: int, project_update: ProjectUpdate) -> Project:
    """Replace the project's details; owners and participants may both do this."""
    project = get_project(session, user, project_id)
    return project_repository.update_project(
        session,
        project,
        name=project_update.name,
        description=project_update.description,
    )


def delete_project(session: Session, storage: Storage, user: User, project_id: int) -> None:
    """Delete the project with its documents and their files; only its owner may do this."""
    membership = _get_membership(session, user, project_id)
    if membership.role != ProjectRole.OWNER:
        raise NotProjectOwnerError(project_id)

    project = membership.project
    storage_keys = [document.storage_key for document in project.documents]
    project_repository.delete_project(session, project)
    # Removed after the commit: a failure here leaves orphaned files, never documents without one.
    for key in storage_keys:
        storage.delete(key)
