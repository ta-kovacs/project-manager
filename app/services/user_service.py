from app.db.interface import ConflictError, Database
from app.db.records import User
from app.schemas.user_schema import UserCreate
from app.security import hash_password, verify_dummy_password, verify_password


class UsernameTakenError(Exception):
    pass


def create_user(db: Database, user_create: UserCreate) -> User:
    # Passwords are checked to match by the UserCreate schema.
    if db.users.get_by_username(user_create.username) is not None:
        raise UsernameTakenError(user_create.username)

    try:
        user = db.users.create(username=user_create.username, password_hash=hash_password(user_create.password))
        db.commit()
    except ConflictError as error:
        # Another request registered the same username between the check and the insert.
        db.rollback()
        raise UsernameTakenError(user_create.username) from error
    return user


def authenticate(db: Database, username: str, password: str) -> User | None:
    """Return the user if the credentials are valid, otherwise None."""
    user = db.users.get_by_username(username)
    if user is None:
        verify_dummy_password(password)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
