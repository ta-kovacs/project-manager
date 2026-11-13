import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import INTERNAL_API_TOKEN
from app.db import get_db
from app.db.orm import users as user_repository
from app.db.orm.models.user import User
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


# Internal endpoints (called by our own AWS Lambda functions, not by users) send the shared
# INTERNAL_API_TOKEN as `Authorization: Bearer <token>` instead of a user's access token.
_internal_bearer_auth = HTTPBearer(auto_error=False, description="INTERNAL_API_TOKEN shared with the Lambda functions")


def require_internal_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_internal_bearer_auth),
) -> None:
    """Rejects the request unless it carries INTERNAL_API_TOKEN; with no token configured, rejects all."""
    if (
        INTERNAL_API_TOKEN is None
        or credentials is None
        # constant-time comparison, so response times don't reveal how much of a guess was right
        or not hmac.compare_digest(credentials.credentials.encode(), INTERNAL_API_TOKEN.encode())
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token",
            headers={"WWW-Authenticate": "Bearer"},
        )
