from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_ACCESS, DATABASE_URL
from app.db.interface import Database
from app.db.orm import OrmDatabase
from app.db.sql import SqlDatabase
from app.db.sql.connection import connect

engine = create_engine(DATABASE_URL, echo=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Database]:
    """FastAPI dependency: a Database for one request, using the DATABASE_ACCESS backend.

    Changes a request doesn't commit are rolled back when it ends.
    """
    if DATABASE_ACCESS == "sql":
        connection = connect(DATABASE_URL)
        try:
            yield SqlDatabase(connection)
        finally:
            connection.close()  # without a commit, this rolls back
    elif DATABASE_ACCESS == "orm":
        with SessionLocal() as session:
            yield OrmDatabase(session)
    else:
        raise RuntimeError(f"Unknown DATABASE_ACCESS {DATABASE_ACCESS!r} (expected 'orm' or 'sql')")
