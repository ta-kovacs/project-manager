"""DELETE /document/{id}: delete a document and remove it from its project (project owner only)."""

import pytest

from app.storage import StoredFileNotFoundError


@pytest.fixture
def assert_still_exists(download_document, get_project_info, document, document_content):
    """Checks that `document` is still listed on its project and still serves its file."""

    def _assert_still_exists():
        assert download_document(document.id).content == document_content
        documents = get_project_info(document.project_id).json()["documents"]
        assert [d["id"] for d in documents] == [document.id]

    return _assert_still_exists


def test_delete_document_by_owner(delete_document, download_document, get_project_info, document):
    response = delete_document(document.id)

    assert response.status_code == 204
    assert response.content == b""
    assert download_document(document.id).status_code == 404
    assert get_project_info(document.project_id).json()["documents"] == []


def test_delete_document_removes_stored_file(delete_document, document, storage):
    storage_key = document.storage_key

    delete_document(document.id)

    with pytest.raises(StoredFileNotFoundError):
        storage.load(storage_key)


def test_delete_document_without_stored_file(delete_document, document, storage):
    storage.delete(document.storage_key)

    assert delete_document(document.id).status_code == 204


def test_delete_document_twice_is_not_found(delete_document, document):
    delete_document(document.id)

    assert delete_document(document.id).status_code == 404


def test_delete_document_by_participant_is_forbidden(delete_document, document, participant_auth, assert_still_exists):
    response = delete_document(document.id, auth=participant_auth)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the project owner can delete documents"
    assert_still_exists()


def test_delete_document_by_non_member_is_not_found(delete_document, document, other_auth, assert_still_exists):
    response = delete_document(document.id, auth=other_auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"
    assert_still_exists()


def test_delete_document_unknown_document_is_not_found(delete_document):
    response = delete_document(999)

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


def test_delete_document_requires_authentication(delete_document, document, bad_auth, assert_still_exists):
    response = delete_document(document.id, auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert_still_exists()
