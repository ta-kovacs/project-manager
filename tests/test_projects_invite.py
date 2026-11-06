"""POST /project/{id}/invite?user=<login>: grant a user participant access (owner only)."""
import pytest

from app.models.project_user import ProjectUser


@pytest.fixture
def invitee(other_auth):
    """Username of a registered user who isn't a member of `project` yet."""
    return other_auth.username


@pytest.fixture
def third_auth(register, bearer_auth):
    """Access token of a third registered user."""
    response = register(username="carol", password="carols-password")
    assert response.status_code == 201, response.text
    return bearer_auth("carol", "carols-password")


def test_invite_user_returns_membership(invite_user, project, invitee):
    response = invite_user(project["id"], invitee)

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "project_id": project["id"],
        "user": {"id": body["user"]["id"], "username": invitee},
        "role": "participant",
    }


def test_invited_user_gets_participant_access(
    invite_user, get_project_info, list_projects, update_project_info, delete_project, project, invitee, other_auth
):
    invite_user(project["id"], invitee)

    # TASK.md: participants can see and modify the project, but not delete it.
    assert get_project_info(project["id"], auth=other_auth).status_code == 200
    assert [p["id"] for p in list_projects(auth=other_auth).json()] == [project["id"]]
    assert update_project_info(project["id"], auth=other_auth).status_code == 200
    assert delete_project(project["id"], auth=other_auth).status_code == 403


def test_invite_user_by_participant_is_forbidden(invite_user, project, participant_auth, third_auth, db_session):
    response = invite_user(project["id"], third_auth.username, auth=participant_auth)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the project owner can invite users"
    assert db_session.query(ProjectUser).count() == 2  # owner + participant only


def test_invite_user_by_non_member_is_not_found(invite_user, project, other_auth, third_auth):
    response = invite_user(project["id"], third_auth.username, auth=other_auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_invite_user_unknown_project_is_not_found(invite_user, invitee):
    response = invite_user(999, invitee)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_invite_unknown_user_is_not_found(invite_user, project):
    response = invite_user(project["id"], "nobody")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.parametrize(
    "existing_member",
    [
        pytest.param("participant", id="participant"),
        pytest.param("owner", id="owner-themselves"),
    ],
)
def test_invite_existing_member_conflicts(
    invite_user, project, credentials, participant_auth, db_session, existing_member
):
    username = participant_auth.username if existing_member == "participant" else credentials["username"]

    response = invite_user(project["id"], username)

    assert response.status_code == 409
    assert response.json()["detail"] == "User already has access to the project"
    assert db_session.query(ProjectUser).count() == 2


@pytest.mark.parametrize("username", [pytest.param(None, id="missing"), pytest.param("", id="empty")])
def test_invite_user_without_login_is_rejected(invite_user, project, username):
    response = invite_user(project["id"], username)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "user"]


def test_invite_user_requires_authentication(invite_user, project, invitee, bad_auth, db_session):
    response = invite_user(project["id"], invitee, auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert db_session.query(ProjectUser).count() == 1  # only the owner
