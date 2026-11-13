"""Create the schema in an empty PostgreSQL database from schema.sql: `python -m app.db.sql`.

Uses DATABASE_URL, like the app. This is the no-ORM alternative to `alembic upgrade head`; afterwards run
`alembic stamp head` if the database should be migrated with Alembic from then on.
"""

from app.config import DATABASE_URL
from app.db.sql.connection import connect
from app.db.sql.schema import create_schema


def main() -> None:
    with connect(DATABASE_URL) as connection:
        create_schema(connection)
        connection.commit()
        print(f"Created the schema in database {connection.info.dbname!r} on {connection.info.host}")


if __name__ == "__main__":
    main()
