"""POST /internal/projects/{id}/rejected-files: the storage-usage Lambda reports files it deleted from S3."""

from tests.helpers import BearerAuth


def test_rejected_files_remove_their_documents(
    report_rejected_files, list_project_documents, storage_used, project, make_document
):
    kept = make_document(project["id"], filename="kept.pdf", content=b"x" * 10)
    rejected = make_document(project["id"], filename="big.pdf", content=b"x" * 30)

    response = report_rejected_files(project["id"], [rejected.storage_key])

    assert response.status_code == 200
    assert response.json() == {"removed_document_ids": [rejected.id]}
    assert [d["id"] for d in list_project_documents(project["id"]).json()] == [kept.id]
    assert storage_used(project["id"]) == 10


def test_several_files_can_be_rejected_at_once(report_rejected_files, storage_used, project, make_document):
    first = make_document(project["id"], filename="a.pdf", content=b"x" * 10)
    second = make_document(project["id"], filename="b.pdf", content=b"x" * 20)

    response = report_rejected_files(project["id"], [second.storage_key, first.storage_key, second.storage_key])

    assert response.json() == {"removed_document_ids": [second.id, first.id]}
    assert storage_used(project["id"]) == 0


def test_keys_of_no_document_are_ignored(report_rejected_files, storage_used, project, document):
    # e.g. a file put into the bucket without the API
    response = report_rejected_files(project["id"], [f"projects/{project['id']}/documents/unknown"])

    assert response.status_code == 200
    assert response.json() == {"removed_document_ids": []}
    assert storage_used(project["id"]) == document.size_bytes


def test_another_projects_documents_are_not_removed(
    report_rejected_files, create_project, make_document, project, other_auth, db
):
    other_project = create_project(name="Bob's project", auth=other_auth).json()
    other_document = make_document(other_project["id"], filename="plan.pdf")

    response = report_rejected_files(project["id"], [other_document.storage_key])

    assert response.json() == {"removed_document_ids": []}
    assert db.documents.get(other_document.id) == other_document


def test_rejected_files_of_a_missing_project_are_not_found(report_rejected_files, internal_token):
    response = report_rejected_files(999, ["projects/999/documents/a"])

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_an_empty_list_is_rejected(report_rejected_files, project, internal_token):
    assert report_rejected_files(project["id"], []).status_code == 422


def test_rejected_files_require_the_internal_token(report_rejected_files, project, document, auth, db):
    for credentials in (None, BearerAuth("wrong"), auth):
        response = report_rejected_files(project["id"], [document.storage_key], auth=credentials)

        assert response.status_code == 401
    assert db.documents.get(document.id) == document
