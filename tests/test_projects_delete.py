"""DELETE /project/{id}: delete a project and its documents (owner only)."""
from app.models.document import Document
from app.models.project import Project
from app.models.project_user import ProjectUser


def test_delete_project_by_owner(delete_project, get_project_info, list_projects, project):
    response = delete_project(project["id"])

    assert response.status_code == 204
    assert response.content == b""
    assert get_project_info(project["id"]).status_code == 404
    assert list_projects().json() == []


def test_delete_project_removes_documents_and_memberships(
    delete_project, project, document, participant_auth, db_session
):
    delete_project(project["id"])

    assert db_session.query(Project).count() == 0
    assert db_session.query(Document).count() == 0
    assert db_session.query(ProjectUser).count() == 0


def test_delete_project_twice_is_not_found(delete_project, project):
    delete_project(project["id"])

    assert delete_project(project["id"]).status_code == 404


def test_delete_project_by_participant_is_forbidden(delete_project, get_project_info, project, participant_auth):
    response = delete_project(project["id"], auth=participant_auth)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the project owner can delete it"
    assert get_project_info(project["id"]).status_code == 200


def test_delete_project_by_non_member_is_not_found(delete_project, get_project_info, project, other_auth):
    response = delete_project(project["id"], auth=other_auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
    assert get_project_info(project["id"]).status_code == 200


def test_delete_project_unknown_project_is_not_found(delete_project):
    response = delete_project(999)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_delete_project_requires_authentication(delete_project, get_project_info, project, bad_auth):
    response = delete_project(project["id"], auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Basic"
    assert get_project_info(project["id"]).status_code == 200
