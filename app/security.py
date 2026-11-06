from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pwdlib import PasswordHash

from app.config import SHARE_LINK_MAX_AGE, SHARE_SECRET_KEY

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
