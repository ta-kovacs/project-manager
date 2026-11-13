"""Projects and their members; callers for the /projects and /project/{id} endpoints."""

import pytest

from app.models.project_user import ProjectRole, ProjectUser
from app.models.user import User
from tests.helpers import payload


@pytest.fixture
def project_data():
    """Valid data for a new project."""
    return {"name": "Apollo", "description": "Land on the moon"}


@pytest.fixture
def create_project(client, auth, project_data):
    """POST /projects as the default user; pass fields to override them, `exclude` to leave some out,
    `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _create_project(*, auth=default_auth, exclude=(), **overrides):
        return client.post("/projects", json=payload(project_data, overrides, exclude), auth=auth)

    return _create_project


@pytest.fixture
def list_projects(client, auth):
    """GET /projects as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _list_projects(*, auth=default_auth):
        return client.get("/projects", auth=auth)

    return _list_projects


@pytest.fixture
def project(create_project):
    """A project owned by the default user; returns its POST /projects response body."""
    response = create_project()
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def participant_auth(project, other_auth, db_session):
    """Credentials of the second user, added to `project` as a participant.

    The membership is inserted directly, so tests of other endpoints don't depend on the invite endpoint.
    """
    other_user = db_session.query(User).filter_by(username=other_auth.username).one()
    db_session.add(ProjectUser(project_id=project["id"], user_id=other_user.id, role=ProjectRole.PARTICIPANT))
    db_session.commit()
    return other_auth


@pytest.fixture
def get_project_info(client, auth):
    """GET /project/{id}/info as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _get_project_info(project_id, *, auth=default_auth):
        return client.get(f"/project/{project_id}/info", auth=auth)

    return _get_project_info


@pytest.fixture
def updated_data():
    """Valid replacement details for a project."""
    return {"name": "Artemis", "description": "Back to the moon"}


@pytest.fixture
def update_project_info(client, auth, updated_data):
    """PUT /project/{id}/info as the default user; pass fields to override them, `exclude` to leave
    some out, `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _update_project_info(project_id, *, auth=default_auth, exclude=(), **overrides):
        return client.put(
            f"/project/{project_id}/info",
            json=payload(updated_data, overrides, exclude),
            auth=auth,
        )

    return _update_project_info


@pytest.fixture
def delete_project(client, auth):
    """DELETE /project/{id} as the default user; pass `auth` to send other credentials (None for none)."""
    default_auth = auth

    def _delete_project(project_id, *, auth=default_auth):
        return client.delete(f"/project/{project_id}", auth=auth)

    return _delete_project
