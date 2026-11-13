"""The database backend without the ORM: hand-written SQL (and schema.sql) on a plain psycopg connection.

No SQLAlchemy at all: queries are SQL strings with %(name)s parameters, run with psycopg, the PostgreSQL
driver. Rows come back as dicts and the repositories turn them into app.db.records themselves.
PostgreSQL only.
"""

import psycopg

from app.db.sql.documents import SqlDocumentRepository
from app.db.sql.projects import SqlProjectRepository
from app.db.sql.users import SqlUserRepository


class SqlDatabase:
    """A unit of work over one psycopg connection."""

    def __init__(self, connection: psycopg.Connection):
        self.connection = connection
        self.users = SqlUserRepository(connection)
        self.projects = SqlProjectRepository(connection)
        self.documents = SqlDocumentRepository(connection)

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()
