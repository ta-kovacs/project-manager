"""Opening psycopg connections for the SQL backend."""

import psycopg
from psycopg.rows import dict_row


def conninfo(database_url: str) -> str:
    """The libpq connection URI for DATABASE_URL.

    DATABASE_URL names the driver for SQLAlchemy (postgresql+psycopg://...); libpq only accepts
    postgresql:// (or postgres://).
    """
    scheme, separator, rest = database_url.partition("://")
    dialect = scheme.split("+", 1)[0]
    if not separator or dialect not in ("postgresql", "postgres"):
        raise ValueError(f"the SQL backend needs a PostgreSQL database, not {scheme!r}")
    return f"postgresql://{rest}"


def connect(database_url: str) -> psycopg.Connection:
    """A new connection whose rows are dicts (column name -> value).

    Like every psycopg connection it starts a transaction with the first statement: changes are kept only
    after commit(), and closing the connection without committing rolls them back.
    """
    return psycopg.connect(conninfo(database_url), row_factory=dict_row)
