"""GET /project/{id}/documents: all of a project's documents, if the caller has access."""

import pytest


def as_json(document):
    return {
        "id": document.id,
        "original_filename": document.original_filename,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
    }


@pytest.mark.parametrize("caller", ["auth", "participant_auth"], ids=["owner", "participant"])
def test_list_project_documents_returns_documents(list_project_documents, project, document, request, caller):
    response = list_project_documents(project["id"], auth=request.getfixturevalue(caller))

    assert response.status_code == 200
    assert response.json() == [as_json(document)]


def test_list_project_documents_empty_project(list_project_documents, project):
    response = list_project_documents(project["id"])

    assert response.status_code == 200
    assert response.json() == []


def test_list_project_documents_in_creation_order(list_project_documents, project, make_document):
    documents = [make_document(project["id"], filename=name) for name in ("b.pdf", "a.pdf", "c.pdf")]

    assert list_project_documents(project["id"]).json() == [as_json(d) for d in documents]


def test_list_project_documents_only_includes_this_project(
    list_project_documents, create_project, project, document, make_document
):
    other_project = create_project(name="Gemini").json()
    make_document(other_project["id"], filename="other.pdf")

    assert list_project_documents(project["id"]).json() == [as_json(document)]


def test_list_project_documents_non_member_gets_not_found(list_project_documents, project, other_auth):
    response = list_project_documents(project["id"], auth=other_auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_list_project_documents_unknown_project_is_not_found(list_project_documents):
    response = list_project_documents(999)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_list_project_documents_non_integer_id_is_rejected(list_project_documents):
    assert list_project_documents("abc").status_code == 422


def test_list_project_documents_requires_authentication(list_project_documents, project, bad_auth):
    response = list_project_documents(project["id"], auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
