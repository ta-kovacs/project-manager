"""The per-project storage limit (PROJECT_STORAGE_LIMIT) and the storage usage it is checked against.

`project_storage_limit` lowers the limit to 64 bytes.
"""

import pytest

from app.models.project import Project

LIMIT_DETAIL = "The project's documents can take up at most 64 bytes in total"


def test_new_project_uses_no_storage(project):
    assert project["storage_used_bytes"] == 0


def test_upload_records_sizes_and_usage(upload_documents, storage_used, project, upload_files):
    body = upload_documents(project["id"]).json()

    assert [d["size_bytes"] for d in body] == [len(content) for _, content in upload_files]
    assert storage_used(project["id"]) == sum(len(content) for _, content in upload_files)


def test_upload_up_to_the_limit_is_accepted(upload_documents, storage_used, project, project_storage_limit):
    response = upload_documents(project["id"], files=[("a.pdf", b"x" * 40), ("b.pdf", b"x" * 24)])

    assert response.status_code == 201
    assert storage_used(project["id"]) == project_storage_limit


def test_upload_over_the_limit_is_rejected(
    upload_documents, list_project_documents, storage_used, stored_files, project, project_storage_limit
):
    upload_documents(project["id"], files=[("a.pdf", b"x" * 40)])

    response = upload_documents(project["id"], files=[("b.pdf", b"x" * 20), ("c.pdf", b"x" * 5)])

    assert response.status_code == 413
    assert response.json()["detail"] == LIMIT_DETAIL
    # Nothing of the rejected upload is kept, and its reservation is released.
    assert [d["original_filename"] for d in list_project_documents(project["id"]).json()] == ["a.pdf"]
    assert len(stored_files()) == 1
    assert storage_used(project["id"]) == 40


def test_limit_applies_per_project(upload_documents, create_project, project, project_storage_limit):
    upload_documents(project["id"], files=[("a.pdf", b"x" * 60)])
    other = create_project(name="Gemini").json()

    assert upload_documents(other["id"], files=[("b.pdf", b"x" * 60)]).status_code == 201


def test_failed_upload_releases_reservation(upload_documents, storage_used, storage, project, monkeypatch):
    def broken_save(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(storage, "save", broken_save)

    with pytest.raises(OSError):
        upload_documents(project["id"])
    monkeypatch.undo()
    assert storage_used(project["id"]) == 0


def test_replace_adjusts_usage_by_the_size_difference(replace_document, storage_used, project, document):
    before, old_size = storage_used(project["id"]), document.size_bytes

    replace_document(document.id, content=b"PK" + b"x" * 98)

    assert storage_used(project["id"]) == before - old_size + 100


def test_replace_growing_over_the_limit_is_rejected(
    replace_document, download_document, storage_used, project, make_document, project_storage_limit
):
    document = make_document(project["id"], content=b"x" * 30)
    make_document(project["id"], filename="other.pdf", content=b"x" * 30)

    response = replace_document(document.id, content=b"x" * 35)

    assert response.status_code == 413
    assert response.json()["detail"] == LIMIT_DETAIL
    assert download_document(document.id).content == b"x" * 30
    assert storage_used(project["id"]) == 60


def test_replace_shrinking_is_accepted_even_over_the_limit(
    replace_document, storage_used, project, make_document, project_storage_limit
):
    # e.g. the limit was lowered after the project filled up
    document = make_document(project["id"], content=b"x" * 100)

    response = replace_document(document.id, content=b"x" * 10)

    assert response.status_code == 200
    assert storage_used(project["id"]) == 10


def test_delete_releases_the_document_size(delete_document, storage_used, project, make_document):
    document = make_document(project["id"], content=b"x" * 30)
    make_document(project["id"], filename="other.pdf", content=b"x" * 12)

    delete_document(document.id)

    assert storage_used(project["id"]) == 12


def test_document_of_unknown_size_counts_fully_when_replaced(
    replace_document, delete_document, storage_used, project, document, db_session
):
    # Documents uploaded before sizes were recorded have size_bytes NULL.
    document.size_bytes = None
    db_session.commit()
    before = storage_used(project["id"])

    replace_document(document.id, content=b"PK" + b"x" * 8)

    assert storage_used(project["id"]) == before + 10


def test_usage_never_goes_below_zero(delete_document, storage_used, project, document, db_session):
    # e.g. the Lambda measured less than the API had counted
    db_session.get(Project, project["id"]).storage_used_bytes = 5
    db_session.commit()

    delete_document(document.id)

    assert storage_used(project["id"]) == 0
