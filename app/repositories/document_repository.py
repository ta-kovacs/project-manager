from sqlalchemy.orm import Session

from app.models.document import Document


def get(session: Session, document_id: int) -> Document | None:
    return session.get(Document, document_id)


def update(session: Session, document: Document, storage_key: str, original_filename: str, content_type: str) -> Document:
    document.storage_key = storage_key
    document.original_filename = original_filename
    document.content_type = content_type
    session.commit()
    session.refresh(document)
    return document


def delete(session: Session, document: Document) -> None:
    session.delete(document)
    session.commit()
