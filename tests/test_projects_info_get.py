"""GET /project/{id}/info: a project's full info, if the caller has access."""
import pytest


@pytest.mark.parametrize("caller", ["auth", "participant_auth"], ids=["owner", "participant"])
def test_get_project_info_returns_full_info(get_project_info, project, request, caller):
    response = get_project_info(project["id"], auth=request.getfixturevalue(caller))

    assert response.status_code == 200
    assert response.json() == project


def test_get_project_info_non_member_gets_not_found(get_project_info, project, other_auth):
    response = get_project_info(project["id"], auth=other_auth)

    # Same as a missing project, so other users' project ids aren't revealed.
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_get_project_info_unknown_project_is_not_found(get_project_info):
    response = get_project_info(999)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_get_project_info_non_integer_id_is_rejected(get_project_info):
    assert get_project_info("abc").status_code == 422


def test_get_project_info_requires_authentication(get_project_info, project, bad_auth):
    response = get_project_info(project["id"], auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
