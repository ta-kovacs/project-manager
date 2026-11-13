"""Access tokens (JWT): what create_access_token puts in them and what read_access_token accepts."""

import time
from datetime import datetime, timedelta

import jwt
import pytest

from app import security
from app.config import JWT_SECRET_KEY
from app.security import JWT_ALGORITHM, InvalidAccessTokenError, create_access_token, read_access_token


def _sign(claims, key=JWT_SECRET_KEY, algorithm=JWT_ALGORITHM):
    return jwt.encode(claims, key, algorithm=algorithm)


def _valid_claims(**overrides):
    now = int(time.time())
    return {"sub": "42", "type": "access", "iat": now, "exp": now + 3600, **overrides}


def test_read_returns_the_user_id_the_token_was_created_for():
    assert read_access_token(create_access_token(42)) == 42


def test_token_lasts_one_hour():
    before = int(time.time())
    token = create_access_token(42)
    after = int(time.time())

    claims = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    assert claims["sub"] == "42"
    assert before <= claims["iat"] <= after
    assert claims["exp"] - claims["iat"] == 3600


def test_token_holds_only_the_user_id_and_timing():
    # The token is readable by anyone who has it, so nothing else may end up in it.
    claims = jwt.decode(create_access_token(42), JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

    assert set(claims) == {"sub", "type", "iat", "exp"}


@pytest.mark.parametrize(("age", "valid"), [(3590, True), (3610, False)], ids=["just-valid", "just-expired"])
def test_token_expires_after_one_hour(monkeypatch, age, valid):
    class IssuedEarlier(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) - timedelta(seconds=age)

    monkeypatch.setattr(security, "datetime", IssuedEarlier)
    token = create_access_token(42)
    monkeypatch.undo()

    if valid:
        assert read_access_token(token) == 42
    else:
        with pytest.raises(InvalidAccessTokenError):
            read_access_token(token)


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("not-a-jwt", id="malformed"),
        pytest.param(_sign(_valid_claims(), key="some-other-key-that-is-at-least-32-bytes"), id="wrong-key"),
        pytest.param(_sign(_valid_claims(), key=None, algorithm="none"), id="unsigned"),
        pytest.param(_sign(_valid_claims(exp=int(time.time()) - 1)), id="expired"),
        pytest.param(_sign(_valid_claims(type="share")), id="wrong-type"),
        pytest.param(_sign(_valid_claims(sub="alice")), id="non-numeric-subject"),
        *[
            pytest.param(_sign({k: v for k, v in _valid_claims().items() if k != claim}), id=f"no-{claim}")
            for claim in ("sub", "type", "iat", "exp")
        ],
    ],
)
def test_read_rejects_untrustworthy_tokens(token):
    with pytest.raises(InvalidAccessTokenError):
        read_access_token(token)
