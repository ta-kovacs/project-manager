from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.project_user import ProjectRole

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=True,
    )

    # Bytes of document files the project holds; checked against PROJECT_STORAGE_LIMIT on upload.
    # Denormalized on purpose: the API adjusts it on every upload, replace and delete, and the
    # storage-usage Lambda overwrites it with the total it measures in S3 (see storage_measured_at).
    storage_used_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    # When the storage-usage Lambda last measured storage_used_bytes; NULL until it first does.
    # An older measurement arriving late (e.g. a retried Lambda run) never overwrites a newer one.
    storage_measured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    members: Mapped[list["ProjectUser"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )

    # read-only shortcut; add/remove members through `members`
    users: Mapped[list["User"]] = relationship(
        secondary="project_users",
        viewonly=True,
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="project",
        cascade=("all, delete-orphan")
    )

    @property
    def owner(self) -> "User | None":
        return next((m.user for m in self.members if m.role == ProjectRole.OWNER), None)
