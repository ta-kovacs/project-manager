from sqlalchemy.orm import Session

from app.models.document import Document


def get(session: Session, document_id: int) -> Document | None:
    return session.get(Document, document_id)
