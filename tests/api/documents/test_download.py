"""GET /document/{id}: download a document's file, if the caller has access to its project."""

import pytest


@pytest.mark.parametrize("caller", ["auth", "participant_auth"], ids=["owner", "participant"])
def test_download_document_returns_file(download_document, document, document_content, request, caller):
    response = download_document(document.id, auth=request.getfixturevalue(caller))

    assert response.status_code == 200
    assert response.content == document_content
    assert response.headers["Content-Type"] == "application/pdf"
    assert response.headers["Content-Disposition"] == "attachment; filename=\"spec.pdf\"; filename*=UTF-8''spec.pdf"


def test_download_document_keeps_non_ascii_filename(download_document, project, make_document):
    document = make_document(project["id"], filename="jelentés 2026.pdf")

    disposition = download_document(document.id).headers["Content-Disposition"]

    assert disposition == "attachment; filename=\"jelent?s 2026.pdf\"; filename*=UTF-8''jelent%C3%A9s%202026.pdf"


def test_download_document_non_member_gets_not_found(download_document, document, other_auth):
    response = download_document(document.id, auth=other_auth)

    # Same as a missing document, so other users' document ids aren't revealed.
    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


def test_download_document_unknown_document_is_not_found(download_document):
    response = download_document(999)

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


def test_download_document_missing_file_is_not_found(download_document, document, storage):
    storage.delete(document.storage_key)

    response = download_document(document.id)

    assert response.status_code == 404
    assert response.json()["detail"] == "Document file not found"


def test_download_document_non_integer_id_is_rejected(download_document):
    assert download_document("abc").status_code == 422


def test_download_document_requires_authentication(download_document, document, bad_auth):
    response = download_document(document.id, auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
