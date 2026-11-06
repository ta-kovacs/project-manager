from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.repositories import user_repository
from app.security import InvalidAccessTokenError, read_access_token

# Every protected request sends `Authorization: Bearer <access token from POST /login>`.
# auto_error=False so a missing header gets the same 401 as a bad token, not FastAPI's default.
_bearer_auth = HTTPBearer(auto_error=False, description="Access token (JWT) returned by POST /login")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_auth),
    session: Session = Depends(get_db),
) -> User:
    """The user the access token was issued to.

    The token only identifies the user: project permissions (owner/participant) are always looked up
    in the database, so revoking access or deleting a project takes effect before the token expires.
    """
    if credentials is None:
        raise _unauthorized()
    try:
        user_id = read_access_token(credentials.credentials)
    except InvalidAccessTokenError:
        raise _unauthorized() from None
    user = user_repository.get_by_id(session, user_id)
    if user is None:
        raise _unauthorized()
    return user
