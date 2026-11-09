from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models.project_user import ProjectRole
from app.schemas.user_schema import UserRead

ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]
ProjectDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


class ProjectCreate(BaseModel):
    name: ProjectName
    description: ProjectDescription | None = None


class ProjectUpdate(ProjectCreate):
    """Replaces a project's details: an omitted description is cleared."""


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    content_type: str
    size_bytes: int | None = Field(description="Size of the file in bytes; null if it was uploaded before sizes were recorded")


class ProjectRead(BaseModel):
    """A project's full info: details, owner and documents."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    owner: UserRead
    documents: list[DocumentRead]
    storage_used_bytes: int = Field(description="Bytes of document files the project holds")


class MemberRead(BaseModel):
    """A user's access to a project."""
    model_config = ConfigDict(from_attributes=True)

    project_id: int
    user: UserRead
    role: ProjectRole


class ShareRead(BaseModel):
    """Confirmation that a share link was emailed."""

    project_id: int
    email: EmailStr
    expires_in: int

