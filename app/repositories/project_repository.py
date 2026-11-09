from sqlalchemy import case, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.project import Project
from app.models.project_user import ProjectRole, ProjectUser
from app.models.user import User


def create_project(session: Session, name: str, description: str | None, owner: User) -> Project:
    project = Project(
        name=name,
        description=description,
        members=[ProjectUser(user=owner, role=ProjectRole.OWNER)],
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def list_for_user(session: Session, user_id: int) -> list[Project]:
    """Projects the user is a member of (owner or participant), oldest first."""
    statement = (
        select(Project)
        .join(ProjectUser)
        .where(ProjectUser.user_id == user_id)
        # load owners and documents up front instead of one query per project
        .options(
            selectinload(Project.members).selectinload(ProjectUser.user),
            selectinload(Project.documents),
        )
        .order_by(Project.id)
    )
    return list(session.scalars(statement))


def get_project(session: Session, project_id: int) -> Project | None:
    return session.get(Project, project_id)


def get_membership(session: Session, project_id: int, user_id: int) -> ProjectUser | None:
    """The user's membership in the project (with `.project` and `.role`), or None if they aren't a member."""
    return session.get(ProjectUser, (project_id, user_id))


def update_project(session: Session, project: Project, name: str, description: str | None) -> Project:
    project.name = name
    project.description = description
    session.commit()
    session.refresh(project)
    return project


def delete_project(session: Session, project: Project) -> None:
    """Delete the project; its memberships and documents go with it (ORM cascade)."""
    session.delete(project)
    session.commit()


def add_member(session: Session, project: Project, user: User, role: ProjectRole) -> ProjectUser:
    membership = ProjectUser(project=project, user=user, role=role)
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return membership


def adjust_storage_used(session: Session, project: Project, delta: int, *, limit: int | None = None) -> bool:
    """Add `delta` bytes (negative to release them) to the project's storage counter, without committing.

    With `limit`, the change is only made if the counter stays within it; returns whether it was made.
    The check and the change are one UPDATE, so concurrent uploads can't both slip under the limit.
    The counter never goes below zero.
    """
    new_value = Project.storage_used_bytes + delta
    statement = (
        update(Project)
        .where(Project.id == project.id)
        .values(storage_used_bytes=case((new_value < 0, 0), else_=new_value))
        .execution_options(synchronize_session=False)
    )
    if limit is not None:
        statement = statement.where(new_value <= limit)
    applied = session.execute(statement).rowcount == 1
    # The UPDATE ran in SQL; reload the counter the next time it is read.
    session.expire(project, ["storage_used_bytes"])
    return applied
