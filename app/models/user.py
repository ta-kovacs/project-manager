from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    # TODO: unique=True (+ migration) once login is implemented
    username: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

    # TODO: store a password hash (e.g. bcrypt/argon2), never the plain password
    password: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

