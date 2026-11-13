"""Users and their access tokens: registering, logging in, and invalid credentials."""

import time

import jwt
import pytest

from app.config import JWT_SECRET_KEY
from app.security import JWT_ALGORITHM
from tests.helpers import BearerAuth, payload


@pytest.fixture
def credentials():
    """Valid credentials of the default test user."""
    return {"username": "alice", "password": "S3cret-pass"}


@pytest.fixture
def register(client, credentials):
    """POST /auth with valid data; pass fields to override them, `exclude` to leave some out.

    `repeat_password` follows `password` unless it is overridden itself.
    """

    def _register(*, exclude=(), **overrides):
        password = overrides.get("password", credentials["password"])
        base = {**credentials, "repeat_password": password}
        return client.post("/auth", json=payload(base, overrides, exclude))

    return _register


@pytest.fixture
def login(client, credentials):
    """POST /login with valid credentials; pass fields to override them, `exclude` to leave some out."""

    def _login(*, exclude=(), **overrides):
        return client.post("/login", json=payload(credentials, overrides, exclude))

    return _login


@pytest.fixture
def registered_user(register):
    """The default test user, already registered; returns the POST /auth response body."""
    response = register()
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def bearer_auth(login):
    """Logs in through POST /login and returns a BearerAuth with the issued access token."""

    def _bearer_auth(username, password):
        response = login(username=username, password=password)
        assert response.status_code == 200, response.text
        return BearerAuth(response.json()["access_token"], username)

    return _bearer_auth


@pytest.fixture
def auth(registered_user, credentials, bearer_auth):
    """Access token of the registered default user, for protected endpoints."""
    return bearer_auth(credentials["username"], credentials["password"])


@pytest.fixture
def other_auth(register, bearer_auth):
    """Access token of a second registered user."""
    response = register(username="bob", password="Tr4in-station")
    assert response.status_code == 201, response.text
    return bearer_auth("bob", "Tr4in-station")


def _signed_token(**claims):
    """A JWT signed with the app's key, with exactly the given claims."""
    return jwt.encode(claims, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _bad_tokens():
    now = int(time.time())
    valid = {"sub": "1", "type": "access", "iat": now, "exp": now + 3600}
    return [
        pytest.param(None, id="no-credentials"),
        pytest.param(("alice", "s3cret-pass"), id="basic-credentials"),
        pytest.param(BearerAuth("not-a-jwt"), id="malformed-token"),
        pytest.param(
            BearerAuth(jwt.encode(valid, "some-other-key-that-is-at-least-32-bytes", algorithm=JWT_ALGORITHM)),
            id="wrong-signature",
        ),
        pytest.param(BearerAuth(_signed_token(**{**valid, "iat": now - 7200, "exp": now - 3600})), id="expired-token"),
        pytest.param(BearerAuth(_signed_token(**{**valid, "sub": "999999"})), id="unknown-user"),
        pytest.param(BearerAuth(_signed_token(**{**valid, "type": "share"})), id="wrong-token-type"),
        pytest.param(
            BearerAuth(
                jwt.encode({k: v for k, v in valid.items() if k != "exp"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
            ),
            id="no-expiry",
        ),
        pytest.param(BearerAuth(jwt.encode(valid, None, algorithm="none")), id="unsigned-token"),
    ]


@pytest.fixture(params=_bad_tokens())
def bad_auth(request, registered_user):
    """Each way a protected request can fail to authenticate; tests using it run once per case.

    `registered_user` exists (id 1), so a valid token for them would be accepted.
    """
    return request.param
