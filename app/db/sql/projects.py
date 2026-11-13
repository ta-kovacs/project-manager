from datetime import datetime

import psycopg

from app.db.interface import ConflictError
from app.db.records import Membership, Project, ProjectRole, User
from app.db.sql.documents import documents_by_project

# A project with its owner: every project has exactly one member with the role 'owner'.
_SELECT_PROJECTS = """
SELECT p.id, p.name, p.description, p.storage_used_bytes, p.storage_measured_at,
       u.id AS owner_id, u.username AS owner_username, u.password_hash AS owner_password_hash
FROM projects p
JOIN project_users o ON o.project_id = p.id AND o.role = 'owner'
JOIN users u ON u.id = o.user_id
"""


class SqlProjectRepository:
    def __init__(self, connection: psycopg.Connection):
        self.connection = connection

    def _projects(self, condition: str, params: dict) -> list[Project]:
        rows = self.connection.execute(f"{_SELECT_PROJECTS} WHERE {condition} ORDER BY p.id", params).fetchall()
        documents = documents_by_project(self.connection, [row["id"] for row in rows])
        return [
            Project(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                storage_used_bytes=row["storage_used_bytes"],
                storage_measured_at=row["storage_measured_at"],
                owner=User(
                    id=row["owner_id"], username=row["owner_username"], password_hash=row["owner_password_hash"]
                ),
                documents=tuple(documents.get(row["id"], ())),
            )
            for row in rows
        ]

    def get(self, project_id: int) -> Project | None:
        projects = self._projects("p.id = %(id)s", {"id": project_id})
        return projects[0] if projects else None

    def list_for_user(self, user_id: int) -> list[Project]:
        return self._projects(
            "p.id IN (SELECT project_id FROM project_users WHERE user_id = %(user_id)s)", {"user_id": user_id}
        )

    def create(self, name: str, description: str | None, owner_id: int) -> Project:
        row = self.connection.execute(
            "INSERT INTO projects (name, description) VALUES (%(name)s, %(description)s) RETURNING id",
            {"name": name, "description": description},
        ).fetchone()
        self.add_member(row["id"], owner_id, ProjectRole.OWNER)
        return self.get(row["id"])

    def update(self, project_id: int, name: str, description: str | None) -> Project:
        cursor = self.connection.execute(
            "UPDATE projects SET name = %(name)s, description = %(description)s WHERE id = %(id)s",
            {"id": project_id, "name": name, "description": description},
        )
        if cursor.rowcount != 1:
            raise LookupError(f"project {project_id} doesn't exist")
        return self.get(project_id)

    def delete(self, project_id: int) -> None:
        # Its memberships and documents go with it: their foreign keys are ON DELETE CASCADE.
        self.connection.execute("DELETE FROM projects WHERE id = %(id)s", {"id": project_id})

    def get_membership(self, project_id: int, user_id: int) -> Membership | None:
        row = self.connection.execute(
            "SELECT m.project_id, m.role, u.id, u.username, u.password_hash"
            " FROM project_users m JOIN users u ON u.id = m.user_id"
            " WHERE m.project_id = %(project_id)s AND m.user_id = %(user_id)s",
            {"project_id": project_id, "user_id": user_id},
        ).fetchone()
        if row is None:
            return None
        user = User(id=row["id"], username=row["username"], password_hash=row["password_hash"])
        return Membership(project_id=row["project_id"], user=user, role=ProjectRole(row["role"]))

    def add_member(self, project_id: int, user_id: int, role: ProjectRole) -> Membership:
        try:
            self.connection.execute(
                "INSERT INTO project_users (project_id, user_id, role) VALUES (%(project_id)s, %(user_id)s, %(role)s)",
                {"project_id": project_id, "user_id": user_id, "role": role.value},
            )
        except psycopg.IntegrityError as error:
            raise ConflictError(f"user {user_id} can't be added to project {project_id} as {role}") from error
        return self.get_membership(project_id, user_id)

    def adjust_storage_used(self, project_id: int, delta: int, *, limit: int | None = None) -> bool:
        sql = (
            "UPDATE projects SET storage_used_bytes ="
            " CASE WHEN storage_used_bytes + %(delta)s < 0 THEN 0 ELSE storage_used_bytes + %(delta)s END"
            " WHERE id = %(id)s"
        )
        params = {"id": project_id, "delta": delta}
        if limit is not None:
            sql += " AND storage_used_bytes + %(delta)s <= %(limit)s"
            params["limit"] = limit
        return self.connection.execute(sql, params).rowcount == 1

    def record_measured_storage(self, project_id: int, total_size_bytes: int, measured_at: datetime) -> bool:
        cursor = self.connection.execute(
            "UPDATE projects SET storage_used_bytes = %(total)s, storage_measured_at = %(measured_at)s"
            " WHERE id = %(id)s AND (storage_measured_at IS NULL OR storage_measured_at < %(measured_at)s)",
            {"id": project_id, "total": total_size_bytes, "measured_at": measured_at},
        )
        return cursor.rowcount == 1
