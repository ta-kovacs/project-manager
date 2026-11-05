"""POST /login: check a user's credentials (username, password)."""
import pytest


def test_login_returns_user(login, registered_user):
    response = login()

    assert response.status_code == 200
    # Same public fields as registration, never the password or its hash.
    assert response.json() == registered_user


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
