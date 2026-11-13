"""Sharing projects: invitations, share emails and join links."""

import re

import pytest

from app.security import create_share_token


@pytest.fixture
def invite_user(client, auth):
    """POST /project/{id}/invite?user=<username> as the default user; `username=None` leaves the
    parameter out, `auth` sends other credentials (None for none)."""
    default_auth = auth

    def _invite_user(project_id, username, *, auth=default_auth):
        params = {} if username is None else {"user": username}
        return client.post(f"/project/{project_id}/invite", params=params, auth=auth)

    return _invite_user


@pytest.fixture
def share_project(client, auth):
    """GET /project/{id}/share?with=<email> as the default user; `email=None` leaves the parameter
    out, `auth` sends other credentials (None for none)."""
    default_auth = auth

    def _share_project(project_id, email, *, auth=default_auth):
        params = {} if email is None else {"with": email}
        return client.get(f"/project/{project_id}/share", params=params, auth=auth)

    return _share_project


@pytest.fixture
def emailed_link(mailer):
    """Returns the join link from the most recent email the mailer recorded."""

    def _emailed_link():
        assert mailer.sent, "no email was sent"
        return re.search(r"https?://\S+/join\?token=\S+", mailer.sent[-1]["body"]).group(0)

    return _emailed_link


@pytest.fixture
def share_token(project):
    """A valid share token for `project`."""
    return create_share_token(project["id"], "bob@example.com")


@pytest.fixture
def join_project(client, other_auth):
    """GET /join?token=<token> as the second user (who isn't a member of `project` yet);
    `token=None` leaves the parameter out, `auth` sends other credentials (None for none)."""
    default_auth = other_auth

    def _join_project(token, *, auth=default_auth):
        params = {} if token is None else {"token": token}
        return client.get("/join", params=params, auth=auth)

    return _join_project
