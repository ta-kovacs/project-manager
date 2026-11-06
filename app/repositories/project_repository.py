from sqlalchemy.orm import Session

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
