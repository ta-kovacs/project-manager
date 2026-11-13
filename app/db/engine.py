from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL
from app.db.interface import Database
from app.db.orm import OrmDatabase

engine = create_engine(DATABASE_URL, echo=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Database]:
    """FastAPI dependency: a Database for one request. Uncommitted changes are rolled back at the end."""
    with SessionLocal() as session:
        yield OrmDatabase(session)
