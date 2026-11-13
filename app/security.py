from datetime import UTC, datetime, timedelta

import jwt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pwdlib import PasswordHash

from app.config import ACCESS_TOKEN_MAX_AGE, JWT_SECRET_KEY, SHARE_LINK_MAX_AGE, SHARE_SECRET_KEY

# Argon2id with pwdlib's recommended parameters.
_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


# Verified against when the username doesn't exist, so a failed login takes
# the same time whether or not the user is registered.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def verify_dummy_password(password: str) -> None:
    _password_hash.verify(password, _DUMMY_HASH)


# --- access tokens (JWT) -------------------------------------------------------------------------

JWT_ALGORITHM = "HS256"

# Tells access tokens apart from any other JWT that might ever be signed with the same key.
_ACCESS_TOKEN_TYPE = "access"


class InvalidAccessTokenError(Exception):
    """The access token is malformed, not signed by this service, or expired."""


def create_access_token(user_id: int) -> str:
    """A signed JWT identifying the user; valid for ACCESS_TOKEN_MAX_AGE seconds."""
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "type": _ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=ACCESS_TOKEN_MAX_AGE),
    }
    return jwt.encode(claims, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def read_access_token(token: str) -> int:
    """The user id in an access token; raises InvalidAccessTokenError if it can't be trusted."""
    try:
        # The algorithm is pinned, so a token can't pick a weaker one (e.g. "none") for itself.
        claims = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
        if claims["type"] != _ACCESS_TOKEN_TYPE:
            raise InvalidAccessTokenError()
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        raise InvalidAccessTokenError() from None


# --- share links ---------------------------------------------------------------------------------


class InvalidShareTokenError(Exception):
    """The share token was not issued by this service, or has been tampered with."""


class ExpiredShareTokenError(Exception):
    """The share token is genuine but older than SHARE_LINK_MAX_AGE."""


def _share_serializer() -> URLSafeTimedSerializer:
    # The salt keeps share tokens from being valid for any other signed value.
    return URLSafeTimedSerializer(SHARE_SECRET_KEY, salt="project-share")


def create_share_token(project_id: int, email: str) -> str:
    """A signed, URL-safe token granting access to the project; valid for SHARE_LINK_MAX_AGE."""
    return _share_serializer().dumps({"project_id": project_id, "email": email})


def read_share_token(token: str) -> tuple[int, str]:
    """The (project_id, email) in a share token; raises if it is invalid or expired."""
    try:
        data = _share_serializer().loads(token, max_age=SHARE_LINK_MAX_AGE)
    except SignatureExpired:
        raise ExpiredShareTokenError() from None
    except BadSignature:
        raise InvalidShareTokenError() from None
    return data["project_id"], data["email"]
