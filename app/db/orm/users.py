from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import records
from app.db.interface import ConflictError
from app.db.orm import records as to_record
from app.db.orm.models import User


class OrmUserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: int) -> records.User | None:
        model = self.session.get(User, user_id, populate_existing=True)
        return None if model is None else to_record.user(model)

    def get_by_username(self, username: str) -> records.User | None:
        model = self.session.scalar(select(User).where(User.username == username))
        return None if model is None else to_record.user(model)

    def create(self, username: str, password_hash: str) -> records.User:
        model = User(username=username, password_hash=password_hash)
        self.session.add(model)
        try:
            self.session.flush()
        except IntegrityError as error:
            raise ConflictError(f"username {username!r} is taken") from error
        return to_record.user(model)
