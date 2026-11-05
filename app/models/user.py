from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    username: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        unique=True,
    )

    # Argon2 hash from app.security; the plain password is never stored
    password_hash: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

    memberships: Mapped[list["ProjectUser"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # read-only shortcut; add/remove memberships through `memberships`
    projects: Mapped[list["Project"]] = relationship(
        secondary="project_users",
        viewonly=True,
    )
