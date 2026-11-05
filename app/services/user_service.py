from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import user_repository
from app.schemas.user_schema import UserCreate
from app.security import hash_password


class UsernameTakenError(Exception):
    pass


def create_user(session: Session, user_create: UserCreate) -> User:
    # Passwords are checked to match by the UserCreate schema.
    if user_repository.get_by_username(session, user_create.username) is not None:
        raise UsernameTakenError(user_create.username)

    try:
        return user_repository.create_user(
            session,
            username=user_create.username,
            password_hash=hash_password(user_create.password),
        )
    except IntegrityError:
        # Another request registered the same username between the check and the insert.
        session.rollback()
        raise UsernameTakenError(user_create.username)
