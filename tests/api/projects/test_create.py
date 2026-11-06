"""POST /projects: create a project (name, description); the caller becomes its owner."""
import pytest

from app.models.project import Project
from app.models.project_user import ProjectRole, ProjectUser


def test_create_project_returns_full_info(create_project, project_data, registered_user):
    response = create_project()

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        **project_data,
        "owner": registered_user,
        "documents": [],
    }


def test_create_project_makes_caller_owner(create_project, registered_user, db_session):
    project_id = create_project().json()["id"]

    membership = db_session.get(ProjectUser, (project_id, registered_user["id"]))
    assert membership.role == ProjectRole.OWNER


def test_create_project_description_is_optional(create_project):
    response = create_project(exclude=["description"])

    assert response.status_code == 201
    assert response.json()["description"] is None


def test_create_project_strips_whitespace(create_project):
    body = create_project(name="  Apollo  ", description="  Land on the moon ").json()

    assert body["name"] == "Apollo"
    assert body["description"] == "Land on the moon"


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"name": ""}, id="name-empty"),
        pytest.param({"name": "   "}, id="name-only-whitespace"),
        pytest.param({"name": "x" * 251}, id="name-too-long"),
        pytest.param({"description": "x" * 5001}, id="description-too-long"),
    ],
)
def test_create_project_invalid_data_is_rejected(create_project, db_session, overrides):
    response = create_project(**overrides)

    assert response.status_code == 422
    assert db_session.query(Project).count() == 0


def test_create_project_missing_name_is_rejected(create_project):
    response = create_project(exclude=["name"])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "name"]


def test_create_project_requires_authentication(create_project, bad_auth, db_session):
    response = create_project(auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert db_session.query(Project).count() == 0
