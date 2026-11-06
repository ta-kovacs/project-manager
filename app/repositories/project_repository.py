from sqlalchemy import select
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


def get_membership(session: Session, project_id: int, user_id: int) -> ProjectUser | None:
    """The user's membership in the project (with `.project` and `.role`), or None if they aren't a member."""
    return session.get(ProjectUser, (project_id, user_id))
