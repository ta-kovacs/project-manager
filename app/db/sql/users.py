import psycopg

from app.db.interface import ConflictError
from app.db.records import User

_SELECT = "SELECT id, username, password_hash FROM users"


class SqlUserRepository:
    def __init__(self, connection: psycopg.Connection):
        self.connection = connection

    def _one(self, sql: str, params: dict) -> User | None:
        row = self.connection.execute(sql, params).fetchone()
        return None if row is None else User(**row)

    def get_by_id(self, user_id: int) -> User | None:
        return self._one(f"{_SELECT} WHERE id = %(id)s", {"id": user_id})

    def get_by_username(self, username: str) -> User | None:
        return self._one(f"{_SELECT} WHERE username = %(username)s", {"username": username})

    def create(self, username: str, password_hash: str) -> User:
        try:
            return self._one(
                "INSERT INTO users (username, password_hash) VALUES (%(username)s, %(password_hash)s)"
                " RETURNING id, username, password_hash",
                {"username": username, "password_hash": password_hash},
            )
        except psycopg.IntegrityError as error:
            raise ConflictError(f"username {username!r} is taken") from error
