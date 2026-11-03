from sqlalchemy.orm import Session

from app.schemas.user_schema import UserCreate
from app.repositories import user_repository

def create_user(session: Session, user_create: UserCreate):
    if user_create.password != user_create.repeat_password:
        ## TODO raise an HTTP 400/422 instead of silently returning None
        return

    ## TODO check for existing user
    ## TODO hash the password before storing it

    return user_repository.create_user(
        session = session,
        username = user_create.username,
        password = user_create.password
    )

