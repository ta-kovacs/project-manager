"""POST /auth: create a user (username, password, repeat_password)."""

import pytest

from app.security import hash_password, verify_password


def test_register_returns_created_user(register, credentials):
    response = register()

    assert response.status_code == 201
    body = response.json()
    # Only the public fields come back, never the password or its hash.
    assert body.keys() == {"id", "username"}
    assert body["username"] == credentials["username"]
    assert isinstance(body["id"], int)


def test_register_stores_password_hash_only(register, credentials, db):
    register()

    user = db.users.get_by_username(credentials["username"])
    assert user.password_hash != credentials["password"]
    assert verify_password(credentials["password"], user.password_hash)


@pytest.mark.usefixtures("registered_user")
def test_register_duplicate_username_conflicts(register):
    response = register(password="An0ther-pass")

    assert response.status_code == 409
    assert response.json()["detail"] == "Username is already taken"


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"repeat_password": "different-pass"}, id="password-mismatch"),
        pytest.param({"password": "Short-p4s"}, id="password-too-short"),
        pytest.param({"password": "Aa1" + "x" * 126}, id="password-too-long"),
        pytest.param({"password": "s3cret-pass"}, id="password-without-uppercase"),
        pytest.param({"password": "S3CRET-PASS"}, id="password-without-lowercase"),
        pytest.param({"password": "Secret-pass"}, id="password-without-digit"),
        pytest.param({"password": "Alice-1234x"}, id="password-contains-username"),
        pytest.param({"password": "x-ALICE-2026"}, id="password-contains-username-other-case"),
        pytest.param({"username": "al"}, id="username-too-short"),
        pytest.param({"username": "a" * 251}, id="username-too-long"),
    ],
)
def test_register_invalid_data_is_rejected(register, count_rows, overrides):
    response = register(**overrides)

    assert response.status_code == 422
    assert count_rows("users") == 0


@pytest.mark.parametrize("missing", ["username", "password", "repeat_password"])
def test_register_missing_field_is_rejected(register, missing):
    response = register(exclude=[missing])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", missing]


@pytest.mark.parametrize("password", ["S3cret-pass", "Correct-h0rse-battery", "Zz9" + "x" * 125])
def test_register_strong_password_is_accepted(register, password):
    assert register(password=password).status_code == 201


def test_register_lists_every_broken_password_rule(register):
    response = register(password="alice-lower", repeat_password="something-else")

    assert response.status_code == 422
    message = response.json()["detail"][0]["msg"]
    assert "password must contain an uppercase letter, a digit" in message
    assert "password must not contain the username" in message
    assert "passwords do not match" in message


def test_existing_weak_password_can_still_log_in(db, login):
    # Users registered before the rules were tightened keep their passwords.
    db.users.create("legacy", hash_password("old-weak"))
    db.commit()

    assert login(username="legacy", password="old-weak").status_code == 200
