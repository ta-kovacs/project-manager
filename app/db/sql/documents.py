from collections.abc import Sequence

import psycopg

from app.db.records import Document, NewDocument

COLUMNS = "id, project_id, storage_key, original_filename, content_type, size_bytes"


def documents_by_project(connection: psycopg.Connection, project_ids: Sequence[int]) -> dict[int, list[Document]]:
    """The documents of each of the projects, oldest first (projects without documents are left out)."""
    if not project_ids:
        return {}
    # A Python list is sent as a PostgreSQL array, which ANY() matches against.
    rows = connection.execute(
        f"SELECT {COLUMNS} FROM documents WHERE project_id = ANY(%(project_ids)s) ORDER BY id",
        {"project_ids": list(project_ids)},
    )
    grouped: dict[int, list[Document]] = {}
    for row in rows:
        grouped.setdefault(row["project_id"], []).append(Document(**row))
    return grouped


class SqlDocumentRepository:
    def __init__(self, connection: psycopg.Connection):
        self.connection = connection

    def get(self, document_id: int) -> Document | None:
        row = self.connection.execute(
            f"SELECT {COLUMNS} FROM documents WHERE id = %(id)s", {"id": document_id}
        ).fetchone()
        return None if row is None else Document(**row)

    def list_for_project(self, project_id: int) -> list[Document]:
        return documents_by_project(self.connection, [project_id]).get(project_id, [])

    def create_many(self, project_id: int, documents: Sequence[NewDocument]) -> list[Document]:
        sql = (
            "INSERT INTO documents (project_id, storage_key, original_filename, content_type, size_bytes)"
            " VALUES (%(project_id)s, %(storage_key)s, %(original_filename)s, %(content_type)s, %(size_bytes)s)"
            f" RETURNING {COLUMNS}"
        )
        created = []
        for new in documents:
            params = {
                "project_id": project_id,
                "storage_key": new.storage_key,
                "original_filename": new.original_filename,
                "content_type": new.content_type,
                "size_bytes": new.size_bytes,
            }
            created.append(Document(**self.connection.execute(sql, params).fetchone()))
        return created

    def update(
        self, document_id: int, storage_key: str, original_filename: str, content_type: str, size_bytes: int
    ) -> Document:
        row = self.connection.execute(
            "UPDATE documents SET storage_key = %(storage_key)s, original_filename = %(original_filename)s,"
            " content_type = %(content_type)s, size_bytes = %(size_bytes)s"
            f" WHERE id = %(id)s RETURNING {COLUMNS}",
            {
                "id": document_id,
                "storage_key": storage_key,
                "original_filename": original_filename,
                "content_type": content_type,
                "size_bytes": size_bytes,
            },
        ).fetchone()
        if row is None:
            raise LookupError(f"document {document_id} doesn't exist")
        return Document(**row)

    def delete(self, document_id: int) -> None:
        self.connection.execute("DELETE FROM documents WHERE id = %(id)s", {"id": document_id})
