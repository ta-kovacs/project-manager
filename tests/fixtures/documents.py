"""Project documents and their stored files; callers for the document endpoints."""
import pytest

from app.models.document import Document
from app.routes import documents as document_routes
from app.services import document_service
from app.storage import S3Storage


@pytest.fixture
def document_content():
    """Bytes of the `document` fixture's file."""
    return b"%PDF-1.4 test document"


@pytest.fixture
def make_document(db_session, storage):
    """Attach a PDF to a project, with its file in `storage`; returns the Document.

    Inserted directly, so tests of other endpoints don't depend on the upload endpoint.
    """
    def _make_document(project_id, *, filename="spec.pdf", content=b"%PDF-1.4 test document"):
        document = Document(
            project_id=project_id,
            storage_key=f"projects/{project_id}/documents/{filename}",
            original_filename=filename,
            content_type="application/pdf",
        )
        storage.save(document.storage_key, content, "application/pdf")
        db_session.add(document)
        db_session.commit()
        return document

    return _make_document


@pytest.fixture
def document(project, make_document, document_content):
    """A PDF attached to `project`, with its file in `storage`."""
    return make_document(project["id"], content=document_content)


@pytest.fixture
def download_document(client, auth):
    """GET /document/{id} as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _download_document(document_id, *, auth=default_auth):
        return client.get(f"/document/{document_id}", auth=auth)

    return _download_document


@pytest.fixture
def new_file():
    """A valid replacement file for a document."""
    return {"filename": "report.docx", "content": b"PK\x03\x04 test docx"}


@pytest.fixture
def replace_document(client, auth, new_file):
    """PUT /document/{id} as the default user, uploading `new_file`; pass `filename`/`content` to
    override it, `exclude=["file"]` to send no file, `auth` for other credentials (None for none)."""
    default_auth = auth

    def _replace_document(document_id, *, auth=default_auth, exclude=(), **overrides):
        upload = {**new_file, **overrides}
        files = None if "file" in exclude else {"file": (upload["filename"], upload["content"])}
        return client.put(f"/document/{document_id}", files=files, auth=auth)

    return _replace_document


@pytest.fixture
def max_document_size(monkeypatch):
    """Lowers the document size limit to 16 bytes for the test; returns the limit."""
    limit = 16
    monkeypatch.setattr(document_service, "MAX_DOCUMENT_SIZE", limit)
    monkeypatch.setattr(document_routes, "MAX_DOCUMENT_SIZE", limit)
    return limit


@pytest.fixture
def delete_document(client, auth):
    """DELETE /document/{id} as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _delete_document(document_id, *, auth=default_auth):
        return client.delete(f"/document/{document_id}", auth=auth)

    return _delete_document


@pytest.fixture
def list_project_documents(client, auth):
    """GET /project/{id}/documents as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _list_project_documents(project_id, *, auth=default_auth):
        return client.get(f"/project/{project_id}/documents", auth=auth)

    return _list_project_documents


@pytest.fixture
def upload_files():
    """Valid files for one upload, as (filename, content) pairs."""
    return [("report.pdf", b"%PDF-1.4 report"), ("notes.docx", b"PK\x03\x04 notes")]


@pytest.fixture
def upload_documents(client, auth, upload_files):
    """POST /project/{id}/documents as the default user, uploading `upload_files`; pass `files` to
    upload others ([] for none), `auth` for other credentials (None for none)."""
    default_auth = auth

    def _upload_documents(project_id, *, auth=default_auth, files=None):
        files = upload_files if files is None else files
        multipart = [("files", (name, content)) for name, content in files] or None
        return client.post(f"/project/{project_id}/documents", files=multipart, auth=auth)

    return _upload_documents


@pytest.fixture
def stored_files(storage):
    """Returns the keys of all files currently in `storage` (either backend)."""
    def _stored_files():
        if isinstance(storage, S3Storage):
            response = storage.client.list_objects_v2(Bucket=storage.bucket)
            return [item["Key"] for item in response.get("Contents", [])]
        if not storage.root.exists():
            return []
        return [path.relative_to(storage.root).as_posix() for path in storage.root.rglob("*") if path.is_file()]

    return _stored_files
