"""POST /project/{id}/documents: upload one or more documents to a project (owner or participant)."""
import pytest

from app.services import document_service

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def assert_nothing_stored(list_project_documents, project, stored_files):
    """Checks that the project has no documents and storage holds no files."""
    def _assert_nothing_stored():
        assert list_project_documents(project["id"]).json() == []
        assert stored_files() == []

    return _assert_nothing_stored


@pytest.mark.parametrize("caller", ["auth", "participant_auth"], ids=["owner", "participant"])
def test_upload_documents_returns_created_documents(upload_documents, project, request, caller):
    response = upload_documents(project["id"], auth=request.getfixturevalue(caller))

    assert response.status_code == 201
    body = response.json()
    assert [(d["original_filename"], d["content_type"]) for d in body] == [("report.pdf", PDF), ("notes.docx", DOCX)]
    assert all(isinstance(d["id"], int) for d in body)


def test_upload_documents_are_listed_and_downloadable(
    upload_documents, list_project_documents, download_document, project, upload_files
):
    uploaded = upload_documents(project["id"]).json()

    assert list_project_documents(project["id"]).json() == uploaded
    for document, (_, content) in zip(uploaded, upload_files, strict=True):
        assert download_document(document["id"]).content == content


def test_upload_single_document(upload_documents, project):
    response = upload_documents(project["id"], files=[("spec.pdf", b"%PDF-1.4 spec")])

    assert response.status_code == 201
    assert [d["original_filename"] for d in response.json()] == ["spec.pdf"]


def test_upload_documents_adds_to_existing_documents(upload_documents, list_project_documents, project, document):
    upload_documents(project["id"])

    names = [d["original_filename"] for d in list_project_documents(project["id"]).json()]
    assert names == ["spec.pdf", "report.pdf", "notes.docx"]


def test_upload_documents_up_to_the_file_limit(upload_documents, project):
    files = [(f"doc{i}.pdf", b"%PDF") for i in range(document_service.MAX_FILES_PER_UPLOAD)]

    assert upload_documents(project["id"], files=files).status_code == 201


@pytest.mark.parametrize(
    ("bad_file", "expected_status", "expected_detail"),
    [
        pytest.param(
            ("notes.txt", b"text"), 415, "Only PDF and DOCX documents are accepted: notes.txt", id="unsupported-type"
        ),
        pytest.param(("big.pdf", b"x" * 17), 413, "Documents can be at most 16 bytes: big.pdf", id="too-large"),
        pytest.param(("empty.pdf", b""), 422, "File is empty: empty.pdf", id="empty"),
    ],
)
def test_upload_documents_one_invalid_file_rejects_all(
    upload_documents, project, upload_files, assert_nothing_stored, max_document_size,
    bad_file, expected_status, expected_detail,
):
    # The valid files fit the 16-byte limit, so only `bad_file` is wrong.
    response = upload_documents(project["id"], files=[*upload_files, bad_file])

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    assert_nothing_stored()


def test_upload_documents_too_many_files_is_rejected(upload_documents, project, assert_nothing_stored):
    files = [(f"doc{i}.pdf", b"%PDF") for i in range(document_service.MAX_FILES_PER_UPLOAD + 1)]

    response = upload_documents(project["id"], files=files)

    assert response.status_code == 422
    assert response.json()["detail"] == "At most 10 files can be uploaded at once"
    assert_nothing_stored()


def test_upload_documents_without_files_is_rejected(upload_documents, project):
    response = upload_documents(project["id"], files=[])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "files"]


def test_upload_documents_non_member_gets_not_found(upload_documents, project, other_auth, assert_nothing_stored):
    response = upload_documents(project["id"], auth=other_auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
    assert_nothing_stored()


def test_upload_documents_unknown_project_is_not_found(upload_documents, stored_files):
    response = upload_documents(999)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
    assert stored_files() == []


def test_upload_documents_requires_authentication(upload_documents, project, bad_auth, assert_nothing_stored):
    response = upload_documents(project["id"], auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert_nothing_stored()


def test_upload_documents_storage_failure_removes_written_files(
    upload_documents, project, storage, monkeypatch, assert_nothing_stored
):
    real_save = storage.save
    saved = []

    def save_then_fail(key, data, content_type):
        if saved:
            raise OSError("disk full")
        real_save(key, data, content_type)
        saved.append(key)

    monkeypatch.setattr(storage, "save", save_then_fail)

    with pytest.raises(OSError, match="disk full"):
        upload_documents(project["id"])

    assert len(saved) == 1  # the first file was written before the failure...
    monkeypatch.undo()
    assert_nothing_stored()  # ...and removed again
