"""POST /auth: create a user (username, password, repeat_password)."""

import pytest

from app.db.orm.models.user import User
from app.security import verify_password


def test_register_returns_created_user(register, credentials):
    response = register()

    assert response.status_code == 201
    body = response.json()
    # Only the public fields come back, never the password or its hash.
    assert body.keys() == {"id", "username"}
    assert body["username"] == credentials["username"]
    assert isinstance(body["id"], int)


def test_register_stores_password_hash_only(register, credentials, db_session):
    register()

    user = db_session.query(User).filter_by(username=credentials["username"]).one()
    assert user.password_hash != credentials["password"]
    assert verify_password(credentials["password"], user.password_hash)


@pytest.mark.usefixtures("registered_user")
def test_register_duplicate_username_conflicts(register):
    response = register(password="another-pass")

    assert response.status_code == 409
    assert response.json()["detail"] == "Username is already taken"


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"repeat_password": "different-pass"}, id="password-mismatch"),
        pytest.param({"password": "short"}, id="password-too-short"),
        pytest.param({"password": "x" * 129}, id="password-too-long"),
        pytest.param({"username": "al"}, id="username-too-short"),
        pytest.param({"username": "a" * 251}, id="username-too-long"),
    ],
)
def test_register_invalid_data_is_rejected(register, db_session, overrides):
    response = register(**overrides)

    assert response.status_code == 422
    assert db_session.query(User).count() == 0


@pytest.mark.parametrize("missing", ["username", "password", "repeat_password"])
def test_register_missing_field_is_rejected(register, missing):
    response = register(exclude=[missing])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", missing]
