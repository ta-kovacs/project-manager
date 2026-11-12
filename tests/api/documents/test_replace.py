"""PUT /document/{id}: replace a document's file (owner or participant)."""
import pytest

from app.storage import StoredFileNotFoundError

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def assert_unchanged(download_document, document, document_content):
    """Checks that `document` still serves its original file."""
    def _assert_unchanged():
        response = download_document(document.id)
        assert response.status_code == 200
        assert response.content == document_content
        assert response.headers["Content-Type"] == PDF

    return _assert_unchanged


@pytest.mark.parametrize("caller", ["auth", "participant_auth"], ids=["owner", "participant"])
def test_replace_document_returns_updated_document(replace_document, document, request, caller):
    response = replace_document(document.id, auth=request.getfixturevalue(caller))

    assert response.status_code == 200
    assert response.json() == {"id": document.id, "original_filename": "report.docx", "content_type": DOCX}


def test_replace_document_serves_new_file(replace_document, download_document, document, new_file):
    replace_document(document.id)

    response = download_document(document.id)
    assert response.content == new_file["content"]
    assert response.headers["Content-Type"] == DOCX
    assert 'filename="report.docx"' in response.headers["Content-Disposition"]


def test_replace_document_removes_old_file(replace_document, document, storage):
    old_key = document.storage_key

    replace_document(document.id)

    assert document.storage_key != old_key
    with pytest.raises(StoredFileNotFoundError):
        storage.load(old_key)


@pytest.mark.parametrize(
    ("filename", "stored_name", "content_type"),
    [
        pytest.param("report.pdf", "report.pdf", PDF, id="pdf"),
        pytest.param("report.docx", "report.docx", DOCX, id="docx"),
        pytest.param("REPORT.PDF", "REPORT.PDF", PDF, id="uppercase-extension"),
        pytest.param(r"C:\Users\alice\report.pdf", "report.pdf", PDF, id="windows-path"),
        pytest.param("../../report.pdf", "report.pdf", PDF, id="relative-path"),
    ],
)
def test_replace_document_accepted_files(replace_document, document, filename, stored_name, content_type):
    response = replace_document(document.id, filename=filename)

    assert response.status_code == 200
    assert response.json()["original_filename"] == stored_name
    assert response.json()["content_type"] == content_type


@pytest.mark.parametrize(
    "filename",
    ["notes.txt", "image.png", "legacy.doc", "no-extension", "report.pdf.exe"],
)
def test_replace_document_unsupported_type_is_rejected(replace_document, document, assert_unchanged, filename):
    response = replace_document(document.id, filename=filename)

    assert response.status_code == 415
    assert response.json()["detail"] == "Only PDF and DOCX documents are accepted"
    assert_unchanged()


def test_replace_document_at_size_limit_is_accepted(replace_document, document, max_document_size):
    response = replace_document(document.id, content=b"x" * max_document_size)

    assert response.status_code == 200


def test_replace_document_over_size_limit_is_rejected(
    replace_document, document, assert_unchanged, max_document_size
):
    response = replace_document(document.id, content=b"x" * (max_document_size + 1))

    assert response.status_code == 413
    assert_unchanged()


def test_replace_document_empty_file_is_rejected(replace_document, document, assert_unchanged):
    response = replace_document(document.id, content=b"")

    assert response.status_code == 422
    assert response.json()["detail"] == "File is empty"
    assert_unchanged()


def test_replace_document_missing_file_is_rejected(replace_document, document):
    response = replace_document(document.id, exclude=["file"])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "file"]


def test_replace_document_non_member_gets_not_found(replace_document, document, other_auth, assert_unchanged):
    response = replace_document(document.id, auth=other_auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"
    assert_unchanged()


def test_replace_document_unknown_document_is_not_found(replace_document):
    response = replace_document(999)

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


def test_replace_document_requires_authentication(replace_document, document, bad_auth, assert_unchanged):
    response = replace_document(document.id, auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert_unchanged()
