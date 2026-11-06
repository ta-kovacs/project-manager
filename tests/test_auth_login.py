"""POST /login: exchange a user's credentials (username, password) for a JWT access token."""
import time
from datetime import datetime, timedelta

import jwt
import pytest

from app import security
from app.config import JWT_SECRET_KEY
from app.security import JWT_ALGORITHM, create_access_token, read_access_token
from tests.conftest import BearerAuth


def test_login_returns_access_token(login, registered_user):
    response = login()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert read_access_token(body["access_token"]) == registered_user["id"]


def test_login_token_lasts_one_hour(login, registered_user):
    before = int(time.time())
    token = login().json()["access_token"]
    after = int(time.time())

    claims = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    assert claims["sub"] == str(registered_user["id"])
    assert before <= claims["iat"] <= after
    assert claims["exp"] - claims["iat"] == 3600
    # Nothing secret ends up in the (readable, unencrypted) token.
    assert "password" not in str(claims)


def test_login_token_authorizes_requests(client, login, registered_user):
    token = login().json()["access_token"]

    response = client.get("/projects", auth=BearerAuth(token))

    assert response.status_code == 200


@pytest.mark.parametrize(("age", "status"), [(3590, 200), (3610, 401)], ids=["just-valid", "just-expired"])
def test_token_expires_after_one_hour(client, registered_user, monkeypatch, age, status):
    class IssuedEarlier(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) - timedelta(seconds=age)

    monkeypatch.setattr(security, "datetime", IssuedEarlier)
    token = create_access_token(registered_user["id"])
    monkeypatch.undo()

    assert client.get("/projects", auth=BearerAuth(token)).status_code == status


def test_expired_token_is_rejected(client, registered_user):
    now = int(time.time())
    claims = {"sub": str(registered_user["id"]), "type": "access", "iat": now - 3700, "exp": now - 100}
    token = jwt.encode(claims, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    response = client.get("/projects", auth=BearerAuth(token))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired access token"
    assert response.headers["WWW-Authenticate"] == "Bearer"


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
