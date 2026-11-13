from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.orm import users as user_repository
from app.db.orm.models.user import User
from app.schemas.user_schema import UserCreate
from app.security import hash_password, verify_dummy_password, verify_password


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
    except IntegrityError as error:
        # Another request registered the same username between the check and the insert.
        session.rollback()
        raise UsernameTakenError(user_create.username) from error


def authenticate(session: Session, username: str, password: str) -> User | None:
    """Return the user if the credentials are valid, otherwise None."""
    user = user_repository.get_by_username(session, username)
    if user is None:
        verify_dummy_password(password)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
