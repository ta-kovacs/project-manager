"""PUT /internal/projects/{id}/storage-usage: the storage-usage Lambda reports a project's measured usage."""

import pytest

from app import dependencies
from tests.helpers import BearerAuth

EARLIER = "2026-11-09T10:00:00+00:00"
LATER = "2026-11-09T10:00:05+00:00"


def test_report_replaces_the_projects_usage(report_storage_usage, storage_used, project, document):
    response = report_storage_usage(project["id"], 12345, EARLIER)

    assert response.status_code == 204
    assert storage_used(project["id"]) == 12345


def test_newer_report_wins(report_storage_usage, storage_used, project):
    report_storage_usage(project["id"], 100, EARLIER)

    report_storage_usage(project["id"], 200, LATER)

    assert storage_used(project["id"]) == 200


def test_older_report_arriving_late_is_ignored(report_storage_usage, storage_used, project):
    report_storage_usage(project["id"], 200, LATER)

    response = report_storage_usage(project["id"], 100, EARLIER)

    assert response.status_code == 204
    assert storage_used(project["id"]) == 200


def test_report_times_in_other_timezones_are_compared_correctly(report_storage_usage, storage_used, project):
    report_storage_usage(project["id"], 200, LATER)

    # 11:00:01 in UTC+1 is 10:00:01 UTC: older than LATER.
    report_storage_usage(project["id"], 100, "2026-11-09T11:00:01+01:00")

    assert storage_used(project["id"]) == 200


def test_uploads_after_a_report_add_to_it(report_storage_usage, upload_documents, storage_used, project):
    report_storage_usage(project["id"], 1000, EARLIER)

    upload_documents(project["id"], files=[("a.pdf", b"x" * 10)])

    assert storage_used(project["id"]) == 1010


def test_report_for_missing_project_is_not_found(report_storage_usage, internal_token):
    response = report_storage_usage(999, 0, EARLIER)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


@pytest.mark.parametrize(
    ("total", "measured_at"),
    [
        pytest.param(-1, EARLIER, id="negative-size"),
        pytest.param(10, "2026-11-09T10:00:00", id="no-timezone"),
        pytest.param(10, "yesterday", id="not-a-time"),
    ],
)
def test_invalid_report_is_rejected(report_storage_usage, project, total, measured_at):
    assert report_storage_usage(project["id"], total, measured_at).status_code == 422


def test_report_requires_the_internal_token(report_storage_usage, project, internal_token):
    response = report_storage_usage(project["id"], 10, EARLIER, auth=None)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_internal_token_is_rejected(report_storage_usage, project, internal_token):
    assert report_storage_usage(project["id"], 10, EARLIER, auth=BearerAuth("wrong")).status_code == 401


def test_user_access_token_is_not_an_internal_token(report_storage_usage, project, auth, internal_token):
    assert report_storage_usage(project["id"], 10, EARLIER, auth=auth).status_code == 401


def test_endpoint_is_disabled_without_a_configured_token(report_storage_usage, project, monkeypatch):
    monkeypatch.setattr(dependencies, "INTERNAL_API_TOKEN", None)

    assert report_storage_usage(project["id"], 10, EARLIER).status_code == 401
