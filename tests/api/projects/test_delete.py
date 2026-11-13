"""DELETE /project/{id}: delete a project and its documents (owner only)."""

import pytest

from app.storage import StoredFileNotFoundError


def test_delete_project_by_owner(delete_project, get_project_info, list_projects, project):
    response = delete_project(project["id"])

    assert response.status_code == 204
    assert response.content == b""
    assert get_project_info(project["id"]).status_code == 404
    assert list_projects().json() == []


def test_delete_project_removes_documents_and_memberships(
    delete_project, project, document, participant_auth, count_rows
):
    delete_project(project["id"])

    assert count_rows("projects") == 0
    assert count_rows("documents") == 0
    assert count_rows("project_users") == 0


def test_delete_project_removes_document_files(delete_project, project, document, storage):
    storage_key = document.storage_key

    delete_project(project["id"])

    with pytest.raises(StoredFileNotFoundError):
        storage.load(storage_key)


def test_delete_project_keeps_other_projects_files(
    delete_project, create_project, make_document, project, document, other_auth, storage
):
    other_project = create_project(name="Bob's project", auth=other_auth).json()
    other_document = make_document(other_project["id"], filename="plan.pdf", content=b"bob's file")

    delete_project(project["id"])

    assert storage.load(other_document.storage_key) == b"bob's file"


@pytest.mark.parametrize(
    ("caller", "expected_status"),
    [
        pytest.param("participant_auth", 403, id="participant"),
        pytest.param("other_auth", 404, id="non-member"),
    ],
)
def test_delete_project_refused_keeps_document_files(
    delete_project, project, document, document_content, storage, request, caller, expected_status
):
    response = delete_project(project["id"], auth=request.getfixturevalue(caller))

    assert response.status_code == expected_status
    assert storage.load(document.storage_key) == document_content


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
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert get_project_info(project["id"]).status_code == 200
