"""PUT /project/{id}/info: replace a project's name and description (owner or participant)."""

import pytest


@pytest.mark.parametrize("caller", ["auth", "participant_auth"], ids=["owner", "participant"])
def test_update_project_info_returns_updated_info(update_project_info, project, updated_data, request, caller):
    response = update_project_info(project["id"], auth=request.getfixturevalue(caller))

    assert response.status_code == 200
    assert response.json() == {**project, **updated_data}


def test_update_project_info_is_persisted(update_project_info, get_project_info, project, updated_data):
    update_project_info(project["id"])

    assert get_project_info(project["id"]).json() == {**project, **updated_data}


def test_update_project_info_omitted_description_is_cleared(update_project_info, project):
    response = update_project_info(project["id"], exclude=["description"])

    assert response.status_code == 200
    assert response.json()["description"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"name": ""}, id="name-empty"),
        pytest.param({"name": "   "}, id="name-only-whitespace"),
        pytest.param({"name": "x" * 251}, id="name-too-long"),
        pytest.param({"description": "x" * 5001}, id="description-too-long"),
    ],
)
def test_update_project_info_invalid_data_is_rejected(update_project_info, get_project_info, project, overrides):
    response = update_project_info(project["id"], **overrides)

    assert response.status_code == 422
    assert get_project_info(project["id"]).json() == project


def test_update_project_info_missing_name_is_rejected(update_project_info, project):
    response = update_project_info(project["id"], exclude=["name"])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "name"]


def test_update_project_info_non_member_gets_not_found(update_project_info, project, other_auth, db):
    response = update_project_info(project["id"], auth=other_auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
    assert db.projects.get(project["id"]).name == project["name"]


def test_update_project_info_unknown_project_is_not_found(update_project_info):
    response = update_project_info(999)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_update_project_info_requires_authentication(update_project_info, project, bad_auth, db):
    response = update_project_info(project["id"], auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert db.projects.get(project["id"]).name == project["name"]
