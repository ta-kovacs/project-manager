"""POST /login: exchange a user's credentials (username, password) for a JWT access token.

What the token contains and when it expires is covered in tests/unit/test_security.py.
"""

import pytest

from app.security import read_access_token
from tests.helpers import BearerAuth


def test_login_returns_access_token(login, registered_user):
    response = login()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert read_access_token(body["access_token"]) == registered_user["id"]


def test_login_token_authorizes_requests(client, login, registered_user):
    token = login().json()["access_token"]

    response = client.get("/projects", auth=BearerAuth(token))

    assert response.status_code == 200


@pytest.mark.usefixtures("registered_user")
@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"password": "wrong-password"}, id="wrong-password"),
        pytest.param({"password": "S3CRET-PASS"}, id="password-wrong-case"),
        pytest.param({"username": "nobody"}, id="unknown-username"),
    ],
)
def test_login_invalid_credentials_are_unauthorized(login, overrides):
    response = login(**overrides)

    # The same response in every case, so callers can't tell which usernames exist.
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


def test_login_without_any_users_is_unauthorized(login):
    assert login().status_code == 401


@pytest.mark.parametrize("missing", ["username", "password"])
def test_login_missing_field_is_rejected(login, missing):
    response = login(exclude=[missing])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", missing]
