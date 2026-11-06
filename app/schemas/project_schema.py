from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints

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


class ProjectRead(BaseModel):
    """A project's full info: details, owner and documents."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    owner: UserRead
    documents: list[DocumentRead]


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
