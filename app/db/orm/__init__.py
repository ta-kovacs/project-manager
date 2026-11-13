"""The database backend built on SQLAlchemy ORM models (models/), mapped to records by the repositories."""

from sqlalchemy.orm import Session

from app.db.orm.documents import OrmDocumentRepository
from app.db.orm.projects import OrmProjectRepository
from app.db.orm.users import OrmUserRepository


class OrmDatabase:
    """A unit of work over one ORM session."""

    def __init__(self, session: Session):
        self.session = session
        self.users = OrmUserRepository(session)
        self.projects = OrmProjectRepository(session)
        self.documents = OrmDocumentRepository(session)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
