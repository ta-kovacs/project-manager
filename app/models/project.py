from sqlalchemy import String, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
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

    members: Mapped[list["ProjectUser"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )

    # read-only shortcut; add/remove members through `members`
    users: Mapped[list["User"]] = relationship(
        secondary="project_users",
        viewonly=True,
    )

    @property
    def owner(self) -> "User | None":
        return next((m.user for m in self.members if m.role == ProjectRole.OWNER), None)
