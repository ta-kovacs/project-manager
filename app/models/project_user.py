import enum

from sqlalchemy import Enum, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ProjectRole(str, enum.Enum):
    OWNER = "owner"
    PARTICIPANT = "participant"


class ProjectUser(Base):
    """Membership of a user in a project. Exactly one member per project is the owner."""

    __tablename__ = "project_users"
    __table_args__ = (
        # "which projects can this user access" - the PK only covers lookups by project_id
        Index("ix_project_users_user_id", "user_id"),
        # at most one owner per project
        Index(
            "uq_project_users_one_owner",
            "project_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
            sqlite_where=text("role = 'owner'"),
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    role: Mapped[ProjectRole] = mapped_column(
        Enum(
            ProjectRole,
            name="project_role",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda roles: [r.value for r in roles],
        ),
        nullable=False,
        default=ProjectRole.PARTICIPANT,
    )

    project: Mapped["Project"] = relationship(
        back_populates="members",
    )

    user: Mapped["User"] = relationship(
        back_populates="memberships",
    )
