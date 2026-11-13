"""Turn ORM model instances into the plain records the rest of the app uses (app.db.records)."""

from app.db import records
from app.db.orm.models import Document, Project, ProjectUser, User


def user(model: User) -> records.User:
    return records.User(id=model.id, username=model.username, password_hash=model.password_hash)


def document(model: Document) -> records.Document:
    return records.Document(
        id=model.id,
        project_id=model.project_id,
        storage_key=model.storage_key,
        original_filename=model.original_filename,
        content_type=model.content_type,
        size_bytes=model.size_bytes,
    )


def project(model: Project) -> records.Project:
    owner = model.owner
    if owner is None:
        raise ValueError(f"project {model.id} has no owner")
    return records.Project(
        id=model.id,
        name=model.name,
        description=model.description,
        storage_used_bytes=model.storage_used_bytes,
        storage_measured_at=model.storage_measured_at,
        owner=user(owner),
        documents=tuple(document(d) for d in model.documents),
    )


def membership(model: ProjectUser) -> records.Membership:
    return records.Membership(project_id=model.project_id, user=user(model.user), role=model.role)
