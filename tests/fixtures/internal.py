"""Internal endpoints, called by our own Lambda functions with INTERNAL_API_TOKEN."""

import pytest

from app import dependencies
from tests.helpers import BearerAuth


@pytest.fixture
def internal_token(monkeypatch):
    """Configures INTERNAL_API_TOKEN for the test; returns it."""
    token = "test-internal-token"
    monkeypatch.setattr(dependencies, "INTERNAL_API_TOKEN", token)
    return token


@pytest.fixture
def internal_auth(internal_token):
    """Credentials of the storage-usage Lambda."""
    return BearerAuth(internal_token)


@pytest.fixture
def report_storage_usage(client, internal_auth):
    """PUT /internal/projects/{id}/storage-usage with the internal token; pass `auth` to send other
    credentials (None for none)."""
    default_auth = internal_auth

    def _report_storage_usage(project_id, total_size_bytes, measured_at, *, auth=default_auth):
        return client.put(
            f"/internal/projects/{project_id}/storage-usage",
            json={"total_size_bytes": total_size_bytes, "measured_at": measured_at},
            auth=auth,
        )

    return _report_storage_usage
