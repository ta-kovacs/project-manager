"""GET /projects: every project the caller can access, with its full info."""
import pytest

from app.models.document import Document
from app.models.project_user import ProjectRole, ProjectUser


@pytest.fixture
def projects(create_project):
    """Two projects owned by the default user; returns their POST /projects response bodies."""
    return [create_project(name=name).json() for name in ("Apollo", "Gemini")]


def test_list_projects_empty_when_user_has_none(list_projects):
    response = list_projects()

    assert response.status_code == 200
    assert response.json() == []


def test_list_projects_returns_own_projects_in_creation_order(list_projects, projects):
    response = list_projects()

    assert response.status_code == 200
    assert response.json() == projects


def test_list_projects_excludes_other_users_projects(list_projects, create_project, other_auth, projects):
    create_project(name="Bob's project", auth=other_auth)

    names = [project["name"] for project in list_projects().json()]
    assert names == ["Apollo", "Gemini"]


def test_list_projects_includes_projects_user_participates_in(
    list_projects, create_project, other_auth, registered_user, db_session
):
    bobs_project = create_project(name="Bob's project", auth=other_auth).json()
    db_session.add(
        ProjectUser(project_id=bobs_project["id"], user_id=registered_user["id"], role=ProjectRole.PARTICIPANT)
    )
    db_session.commit()

    listed = list_projects().json()

    assert listed == [bobs_project]
    assert listed[0]["owner"]["username"] == "bob"


def test_list_projects_includes_documents(list_projects, projects, db_session):
    document = Document(
        project_id=projects[0]["id"],
        storage_key="projects/1/spec.pdf",
        original_filename="spec.pdf",
        content_type="application/pdf",
    )
    db_session.add(document)
    db_session.commit()

    apollo, gemini = list_projects().json()

    assert apollo["documents"] == [
        {"id": document.id, "original_filename": "spec.pdf", "content_type": "application/pdf"}
    ]
    assert gemini["documents"] == []


def test_list_projects_requires_authentication(list_projects, bad_auth):
    response = list_projects(auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
