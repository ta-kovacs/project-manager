from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services import user_service

# Every protected request sends `Authorization: Basic <username:password>`.
# TODO: replace with a JWT bearer token issued by POST /login; routes only depend on get_current_user.
_basic_auth = HTTPBasic(description="Username and password of a registered user")


def get_current_user(
    credentials: HTTPBasicCredentials = Depends(_basic_auth),
    session: Session = Depends(get_db),
) -> User:
    user = user_service.authenticate(session, credentials.username, credentials.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user
