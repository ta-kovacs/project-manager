from collections.abc import Callable
from datetime import UTC, datetime

from app.config import SHARE_LINK_MAX_AGE
from app.db.interface import ConflictError, Database
from app.db.records import Membership, Project, ProjectRole, User
from app.mailer import Mailer
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


def create_project(db: Database, user: User, project_create: ProjectCreate) -> Project:
    """Create a project with `user` as its owner."""
    project = db.projects.create(name=project_create.name, description=project_create.description, owner_id=user.id)
    db.commit()
    return project


def list_projects(db: Database, user: User) -> list[Project]:
    """All projects `user` can access."""
    return db.projects.list_for_user(user.id)


def _get_membership(db: Database, user: User, project_id: int) -> Membership:
    membership = db.projects.get_membership(project_id, user.id)
    if membership is None:
        raise ProjectNotFoundError(project_id)
    return membership


def _get_owned_project(db: Database, user: User, project_id: int) -> Project:
    if _get_membership(db, user, project_id).role != ProjectRole.OWNER:
        raise NotProjectOwnerError(project_id)
    return _get_existing_project(db, project_id)


def _get_existing_project(db: Database, project_id: int) -> Project:
    project = db.projects.get(project_id)
    if project is None:
        raise ProjectNotFoundError(project_id)
    return project


def get_project(db: Database, user: User, project_id: int) -> Project:
    """The project, if `user` is its owner or a participant."""
    _get_membership(db, user, project_id)
    return _get_existing_project(db, project_id)


def update_project(db: Database, user: User, project_id: int, project_update: ProjectUpdate) -> Project:
    """Replace the project's details; owners and participants may both do this."""
    _get_membership(db, user, project_id)
    project = db.projects.update(project_id, name=project_update.name, description=project_update.description)
    db.commit()
    return project


def delete_project(db: Database, storage: Storage, user: User, project_id: int) -> None:
    """Delete the project with its documents and their files; only its owner may do this."""
    project = _get_owned_project(db, user, project_id)
    db.projects.delete(project.id)
    db.commit()
    # Removed after the commit: a failure here leaves orphaned files, never documents without one.
    for document in project.documents:
        storage.delete(document.storage_key)


def invite_user(db: Database, user: User, project_id: int, username: str) -> Membership:
    """Give the user `username` participant access to the project; only its owner may do this."""
    project = _get_owned_project(db, user, project_id)
    invitee = db.users.get_by_username(username)
    if invitee is None:
        raise UserNotFoundError(username)
    if db.projects.get_membership(project.id, invitee.id) is not None:
        raise AlreadyMemberError(username)
    try:
        membership = db.projects.add_member(project.id, invitee.id, ProjectRole.PARTICIPANT)
        db.commit()
    except ConflictError as error:
        # Invited by a concurrent request between the check and the insert.
        db.rollback()
        raise AlreadyMemberError(username) from error
    return membership


def share_project(
    db: Database, mailer: Mailer, user: User, project_id: int, email: str, join_url: Callable[[str], str]
) -> None:
    """Email `email` a link that gives whoever opens it participant access; only the owner may do this.

    `join_url` turns a share token into the full GET /join link.
    """
    project = _get_owned_project(db, user, project_id)
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


def join_project(db: Database, user: User, token: str) -> Membership:
    """Give `user` participant access to the project named in a share token.

    Raises security.InvalidShareTokenError / ExpiredShareTokenError for bad tokens and
    ProjectNotFoundError if the project no longer exists. Joining again (or as the owner)
    returns the existing membership unchanged.
    """
    project_id, _email = read_share_token(token)
    project = _get_existing_project(db, project_id)

    existing = db.projects.get_membership(project.id, user.id)
    if existing is not None:
        return existing
    try:
        membership = db.projects.add_member(project.id, user.id, ProjectRole.PARTICIPANT)
        db.commit()
    except ConflictError:
        # Joined through a concurrent request (e.g. the link was opened twice at once).
        db.rollback()
        return db.projects.get_membership(project.id, user.id)
    return membership


def record_measured_storage(db: Database, project_id: int, total_size_bytes: int, measured_at: datetime) -> None:
    """Store the storage usage the storage-usage Lambda measured in S3 for a project.

    A measurement older than the one already stored is ignored (it is not an error): Lambda runs can
    finish, or be retried, out of order. Raises ProjectNotFoundError if the project doesn't exist,
    e.g. because it was deleted after its files changed.
    """
    stored = db.projects.record_measured_storage(project_id, total_size_bytes, measured_at.astimezone(UTC))
    db.commit()
    if not stored:
        _get_existing_project(db, project_id)
