"""schema.sql and the ORM models (the source of the Alembic migrations) describe the same database.

Each is created in turn on the test database (schema.sql through psycopg, the models through SQLAlchemy)
and read back with SQLAlchemy's inspector. schema.sql is written for PostgreSQL, so this needs a
PostgreSQL TEST_DATABASE_URL and is skipped on the default SQLite database.
"""

import pytest
from sqlalchemy import inspect

from app.db.orm.models.base import Base
from app.db.sql.connection import connect
from app.db.sql.schema import TABLES, create_schema, drop_schema
from tests.fixtures.app import POSTGRES, TEST_DATABASE_URL, engine

pytestmark = pytest.mark.skipif(not POSTGRES, reason="schema.sql is for PostgreSQL (set TEST_DATABASE_URL)")


def describe_schema():
    inspector = inspect(engine)
    schema = {}
    for table in sorted(inspector.get_table_names()):
        schema[table] = {
            "columns": {
                column["name"]: (column["nullable"], str(column["type"])) for column in inspector.get_columns(table)
            },
            "primary key": inspector.get_pk_constraint(table)["constrained_columns"],
            "foreign keys": sorted(
                (
                    tuple(fk["constrained_columns"]),
                    fk["referred_table"],
                    tuple(fk["referred_columns"]),
                    fk["options"].get("ondelete"),
                )
                for fk in inspector.get_foreign_keys(table)
            ),
            # By columns: the ORM leaves column-level UNIQUE constraints unnamed.
            "unique": sorted(tuple(u["column_names"]) for u in inspector.get_unique_constraints(table)),
            "indexes": sorted(
                (index["name"], tuple(index["column_names"]), bool(index["unique"]))
                for index in inspector.get_indexes(table)
                if not index.get("duplicates_constraint")
            ),
            "checks": sorted(check["name"] for check in inspector.get_check_constraints(table)),
        }
    return schema


@pytest.fixture
def orm_schema():
    Base.metadata.create_all(engine)
    try:
        return describe_schema()
    finally:
        Base.metadata.drop_all(engine)


@pytest.fixture
def sql_schema():
    with connect(TEST_DATABASE_URL) as connection:
        create_schema(connection)
        connection.commit()
    try:
        return describe_schema()
    finally:
        with connect(TEST_DATABASE_URL) as connection:
            drop_schema(connection)
            connection.commit()


def test_schema_sql_creates_every_table(sql_schema):
    assert set(sql_schema) == set(TABLES)


@pytest.mark.parametrize("table", sorted(TABLES))
def test_schema_sql_matches_the_orm_models(orm_schema, sql_schema, table):
    assert sql_schema[table] == orm_schema[table]
