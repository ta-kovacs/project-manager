from datetime import datetime

from sqlalchemy import case, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import records
from app.db.interface import ConflictError
from app.db.orm import records as to_record
from app.db.orm.models import Project, ProjectUser, User
from app.db.records import ProjectRole


def _projects():
    """Projects with their owner and documents loaded up front, refreshed from the database."""
    return (
        select(Project)
        .options(
            selectinload(Project.members).selectinload(ProjectUser.user),
            selectinload(Project.documents),
        )
        .execution_options(populate_existing=True)
    )


class OrmProjectRepository:
    def __init__(self, session: Session):
        self.session = session

    def _model(self, project_id: int) -> Project | None:
        return self.session.scalar(_projects().where(Project.id == project_id))

    def get(self, project_id: int) -> records.Project | None:
        model = self._model(project_id)
        return None if model is None else to_record.project(model)

    def list_for_user(self, user_id: int) -> list[records.Project]:
        statement = _projects().join(ProjectUser).where(ProjectUser.user_id == user_id).order_by(Project.id)
        return [to_record.project(model) for model in self.session.scalars(statement)]

    def create(self, name: str, description: str | None, owner_id: int) -> records.Project:
        owner = self.session.get(User, owner_id)
        model = Project(
            name=name,
            description=description,
            members=[ProjectUser(user=owner, role=ProjectRole.OWNER)],
        )
        self.session.add(model)
        self.session.flush()
        return self.get(model.id)

    def update(self, project_id: int, name: str, description: str | None) -> records.Project:
        model = self._model(project_id)
        if model is None:
            raise LookupError(f"project {project_id} doesn't exist")
        model.name = name
        model.description = description
        self.session.flush()
        return to_record.project(model)

    def delete(self, project_id: int) -> None:
        model = self._model(project_id)
        if model is not None:
            # memberships and documents go with it (ORM cascade)
            self.session.delete(model)
            self.session.flush()

    def get_membership(self, project_id: int, user_id: int) -> records.Membership | None:
        model = self.session.get(ProjectUser, (project_id, user_id), populate_existing=True)
        return None if model is None else to_record.membership(model)

    def add_member(self, project_id: int, user_id: int, role: ProjectRole) -> records.Membership:
        model = ProjectUser(project_id=project_id, user_id=user_id, role=role)
        self.session.add(model)
        try:
            self.session.flush()
        except IntegrityError as error:
            raise ConflictError(f"user {user_id} can't be added to project {project_id} as {role}") from error
        return self.get_membership(project_id, user_id)

    def adjust_storage_used(self, project_id: int, delta: int, *, limit: int | None = None) -> bool:
        new_value = Project.storage_used_bytes + delta
        statement = (
            update(Project)
            .where(Project.id == project_id)
            .values(storage_used_bytes=case((new_value < 0, 0), else_=new_value))
            .execution_options(synchronize_session=False)
        )
        if limit is not None:
            statement = statement.where(new_value <= limit)
        return self.session.execute(statement).rowcount == 1

    def record_measured_storage(self, project_id: int, total_size_bytes: int, measured_at: datetime) -> bool:
        statement = (
            update(Project)
            .where(
                Project.id == project_id,
                or_(Project.storage_measured_at.is_(None), Project.storage_measured_at < measured_at),
            )
            .values(storage_used_bytes=total_size_bytes, storage_measured_at=measured_at)
            .execution_options(synchronize_session=False)
        )
        return self.session.execute(statement).rowcount == 1
