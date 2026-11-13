from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import records
from app.db.orm import records as to_record
from app.db.orm.models import Document


class OrmDocumentRepository:
    def __init__(self, session: Session):
        self.session = session

    def _model(self, document_id: int) -> Document | None:
        return self.session.get(Document, document_id, populate_existing=True)

    def get(self, document_id: int) -> records.Document | None:
        model = self._model(document_id)
        return None if model is None else to_record.document(model)

    def list_for_project(self, project_id: int) -> list[records.Document]:
        statement = (
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.id)
            .execution_options(populate_existing=True)
        )
        return [to_record.document(model) for model in self.session.scalars(statement)]

    def create_many(self, project_id: int, documents: Sequence[records.NewDocument]) -> list[records.Document]:
        models = [
            Document(
                project_id=project_id,
                storage_key=new.storage_key,
                original_filename=new.original_filename,
                content_type=new.content_type,
                size_bytes=new.size_bytes,
            )
            for new in documents
        ]
        self.session.add_all(models)
        self.session.flush()
        return [to_record.document(model) for model in models]

    def update(
        self, document_id: int, storage_key: str, original_filename: str, content_type: str, size_bytes: int
    ) -> records.Document:
        model = self._model(document_id)
        if model is None:
            raise LookupError(f"document {document_id} doesn't exist")
        model.storage_key = storage_key
        model.original_filename = original_filename
        model.content_type = content_type
        model.size_bytes = size_bytes
        self.session.flush()
        return to_record.document(model)

    def delete(self, document_id: int) -> None:
        model = self._model(document_id)
        if model is not None:
            self.session.delete(model)
            self.session.flush()
