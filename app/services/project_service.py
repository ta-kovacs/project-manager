from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import SHARE_LINK_MAX_AGE
from app.mailer import Mailer
from app.models.project import Project
from app.models.project_user import ProjectRole, ProjectUser
from app.models.user import User
from app.repositories import project_repository, user_repository
from app.schemas.project_schema import ProjectCreate, ProjectUpdate
from app.security import create_share_token, read_share_token
from app.storage import Storage


class ProjectNotFoundError(Exception):
    """The project doesn't exist, or the user isn't a member (the two aren't distinguished)."""


class NotProjectOwnerError(Exception):
    """The user is a member of the project, but the action is reserved for its owner."""


class UserNotFoundError(Exception):
    """No user has the given username."""


class AlreadyMemberError(Exception):
    """The user already has access to the project (as owner or participant)."""


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


def _get_owner_membership(session: Session, user: User, project_id: int) -> ProjectUser:
    membership = _get_membership(session, user, project_id)
    if membership.role != ProjectRole.OWNER:
        raise NotProjectOwnerError(project_id)
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
    project = _get_owner_membership(session, user, project_id).project
    storage_keys = [document.storage_key for document in project.documents]
    project_repository.delete_project(session, project)
    # Removed after the commit: a failure here leaves orphaned files, never documents without one.
    for key in storage_keys:
        storage.delete(key)


def invite_user(session: Session, user: User, project_id: int, username: str) -> ProjectUser:
    """Give the user `username` participant access to the project; only its owner may do this."""
    project = _get_owner_membership(session, user, project_id).project
    invitee = user_repository.get_by_username(session, username)
    if invitee is None:
        raise UserNotFoundError(username)
    if project_repository.get_membership(session, project.id, invitee.id) is not None:
        raise AlreadyMemberError(username)
    try:
        return project_repository.add_member(session, project, invitee, ProjectRole.PARTICIPANT)
    except IntegrityError:
        # Invited by a concurrent request between the check and the insert.
        session.rollback()
        raise AlreadyMemberError(username)


def share_project(
    session: Session, mailer: Mailer, user: User, project_id: int, email: str, join_url: Callable[[str], str]
) -> None:
    """Email `email` a link that gives whoever opens it participant access; only the owner may do this.

    `join_url` turns a share token into the full GET /join link.
    """
    project = _get_owner_membership(session, user, project_id).project
    link = join_url(create_share_token(project.id, email))
    days = SHARE_LINK_MAX_AGE // (24 * 60 * 60)
    mailer.send(
        to=email,
        subject=f'{user.username} shared the project "{project.name}" with you',
        body=(
            f'{user.username} invited you to the project "{project.name}" on Project Manager.\n\n'
            f"Open this link and sign in to join it as a participant:\n{link}\n\n"
            f"The link is valid for {days} days. If you weren't expecting this, you can ignore this email."
        ),
    )


def join_project(session: Session, user: User, token: str) -> ProjectUser:
    """Give `user` participant access to the project named in a share token.

    Raises security.InvalidShareTokenError / ExpiredShareTokenError for bad tokens and
    ProjectNotFoundError if the project no longer exists. Joining again (or as the owner)
    returns the existing membership unchanged.
    """
    project_id, _email = read_share_token(token)
    project = project_repository.get_project(session, project_id)
    if project is None:
        raise ProjectNotFoundError(project_id)

    existing = project_repository.get_membership(session, project.id, user.id)
    if existing is not None:
        return existing
    try:
        return project_repository.add_member(session, project, user, ProjectRole.PARTICIPANT)
    except IntegrityError:
        # Joined through a concurrent request (e.g. the link was opened twice at once).
        session.rollback()
        return project_repository.get_membership(session, project.id, user.id)


def record_measured_storage(session: Session, project_id: int, total_size_bytes: int, measured_at: datetime) -> None:
    """Store the storage usage the storage-usage Lambda measured in S3 for a project.

    A measurement older than the one already stored is ignored (it is not an error): Lambda runs can
    finish, or be retried, out of order. Raises ProjectNotFoundError if the project doesn't exist,
    e.g. because it was deleted after its files changed.
    """
    stored = project_repository.record_measured_storage(
        session, project_id, total_size_bytes, measured_at.astimezone(UTC)
    )
    if not stored and project_repository.get_project(session, project_id) is None:
        raise ProjectNotFoundError(project_id)
