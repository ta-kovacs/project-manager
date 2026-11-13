"""Create and drop the database schema from schema.sql, without the ORM."""

from importlib.resources import files

import psycopg

# Children first, so foreign keys never point at a dropped table.
TABLES = ("documents", "project_users", "projects", "users")


def schema_sql() -> str:
    return files("app.db.sql").joinpath("schema.sql").read_text(encoding="utf-8")


def create_schema(connection: psycopg.Connection) -> None:
    """Create every table and index (in the connection's transaction; the caller commits)."""
    # Without parameters, psycopg sends the whole script at once, so it may hold several statements.
    connection.execute(schema_sql())


def drop_schema(connection: psycopg.Connection) -> None:
    """Drop every table, if it exists (in the connection's transaction; the caller commits)."""
    connection.execute(f"DROP TABLE IF EXISTS {', '.join(TABLES)}")
