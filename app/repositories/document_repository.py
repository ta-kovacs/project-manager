from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


def get(session: Session, document_id: int) -> Document | None:
    return session.get(Document, document_id)


def list_for_project(session: Session, project_id: int) -> list[Document]:
    """The project's documents, oldest first."""
    statement = select(Document).where(Document.project_id == project_id).order_by(Document.id)
    return list(session.scalars(statement))


def create_many(session: Session, documents: list[Document]) -> list[Document]:
    session.add_all(documents)
    session.commit()
    for document in documents:
        session.refresh(document)
    return documents


def update(
    session: Session, document: Document, storage_key: str, original_filename: str, content_type: str, size_bytes: int
) -> Document:
    document.storage_key = storage_key
    document.original_filename = original_filename
    document.content_type = content_type
    document.size_bytes = size_bytes
    session.commit()
    session.refresh(document)
    return document


def delete(session: Session, document: Document) -> None:
    session.delete(document)
    session.commit()
