"""Every endpoint requires an access token, except the few that must work without one.

The per-endpoint tests check authentication for the endpoints that exist today; this one also fails
for a new endpoint that forgets `Depends(get_current_user)`.
"""
import re

import pytest

from app.main import app

# (method, path) of the endpoints anyone may call. Keep this list short and deliberate.
PUBLIC_ENDPOINTS = {
    ("POST", "/auth"),
    ("POST", "/login"),
    ("GET", "/health"),
}


def _endpoints():
    # Read from the OpenAPI schema: FastAPI keeps included routers' routes in private structures.
    # Endpoints registered with include_in_schema=False would not be listed here.
    return sorted(
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    )


def _protected_endpoints():
    return [endpoint for endpoint in _endpoints() if endpoint not in PUBLIC_ENDPOINTS]


def test_public_endpoints_exist():
    # A renamed or removed endpoint must not linger here, quietly exempting whatever reuses the path.
    assert PUBLIC_ENDPOINTS <= set(_endpoints())


def test_there_are_protected_endpoints():
    # Guards the parametrized test below against silently collecting nothing.
    assert len(_protected_endpoints()) >= 10


@pytest.mark.parametrize(
    ("method", "path"),
    [pytest.param(method, path, id=f"{method} {path}") for method, path in _protected_endpoints()],
)
def test_endpoint_requires_access_token(client, method, path):
    # Any value works for path parameters: authentication is checked before the resource is looked up.
    url = re.sub(r"\{[^}]+\}", "1", path)

    response = client.request(method, url)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
