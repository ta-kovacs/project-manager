"""GET /join?token=<token>: join a project through a share link as a participant."""

import pytest

import app.security as security


def test_share_link_from_email_grants_access(
    client, share_project, emailed_link, get_project_info, project, other_auth
):
    # The owner shares the project; a different user opens the emailed link.
    share_project(project["id"], "bob@example.com")

    response = client.get(emailed_link(), auth=other_auth)

    assert response.status_code == 200
    assert response.json()["role"] == "participant"
    assert get_project_info(project["id"], auth=other_auth).status_code == 200


def test_join_project_returns_membership(join_project, share_token, project, other_auth):
    response = join_project(share_token)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "project_id": project["id"],
        "user": {"id": body["user"]["id"], "username": other_auth.username},
        "role": "participant",
    }


def test_joined_user_has_participant_permissions(
    join_project, share_token, update_project_info, delete_project, project, other_auth
):
    join_project(share_token)

    assert update_project_info(project["id"], auth=other_auth).status_code == 200
    assert delete_project(project["id"], auth=other_auth).status_code == 403


def test_join_project_twice_keeps_one_membership(join_project, share_token, count_rows):
    first = join_project(share_token).json()

    second = join_project(share_token)

    assert second.status_code == 200
    assert second.json() == first
    assert count_rows("project_users") == 2  # owner + the joined user


@pytest.mark.parametrize(
    ("caller", "role"),
    [
        pytest.param("auth", "owner", id="owner"),
        pytest.param("participant_auth", "participant", id="participant"),
    ],
)
def test_join_project_existing_member_keeps_role(join_project, share_token, count_rows, request, caller, role):
    member_auth = request.getfixturevalue(caller)  # resolved first: participant_auth adds a member
    members_before = count_rows("project_users")

    response = join_project(share_token, auth=member_auth)

    assert response.status_code == 200
    assert response.json()["role"] == role
    assert count_rows("project_users") == members_before


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("not-a-token", id="garbage"),
        pytest.param("eyJwcm9qZWN0X2lkIjoxfQ.forged.signature", id="forged"),
    ],
)
def test_join_project_invalid_token_is_rejected(join_project, project, count_rows, token):
    response = join_project(token)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid share link"
    assert count_rows("project_users") == 1


def test_join_project_tampered_token_is_rejected(join_project, share_token, count_rows):
    # Change the signature's first character: the last one also carries base64 padding bits that
    # decoding ignores, so changing it can leave the signature valid.
    payload, signature = share_token.rsplit(".", 1)
    tampered = ("B" if signature[0] == "A" else "A") + signature[1:]

    response = join_project(f"{payload}.{tampered}")

    assert response.status_code == 400
    assert count_rows("project_users") == 1


def test_join_project_expired_token_is_gone(join_project, share_token, count_rows, monkeypatch):
    monkeypatch.setattr(security, "SHARE_LINK_MAX_AGE", -1)  # every token is now too old

    response = join_project(share_token)

    assert response.status_code == 410
    assert response.json()["detail"] == "This share link has expired"
    assert count_rows("project_users") == 1


def test_join_deleted_project_is_not_found(join_project, share_token, delete_project, project):
    delete_project(project["id"])

    response = join_project(share_token)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_join_project_without_token_is_rejected(join_project):
    response = join_project(None)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "token"]


def test_join_project_requires_authentication(join_project, share_token, bad_auth, count_rows):
    response = join_project(share_token, auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert count_rows("project_users") == 1
