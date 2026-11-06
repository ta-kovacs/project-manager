"""GET /project/{id}/share?with=<email>: email a join link for the project (owner only)."""
from urllib.parse import parse_qs, urlsplit

import pytest

import app.routes.projects as project_routes
import app.security as security
from app.mailer import MailDeliveryError
from app.security import ExpiredShareTokenError, InvalidShareTokenError, create_share_token, read_share_token

EMAIL = "bob@example.com"


def token_of(link):
    return parse_qs(urlsplit(link).query)["token"][0]


# --- the endpoint ---------------------------------------------------------------------------------

def test_share_project_confirms_email(share_project, project):
    response = share_project(project["id"], EMAIL)

    assert response.status_code == 200
    assert response.json() == {"project_id": project["id"], "email": EMAIL, "expires_in": 7 * 24 * 60 * 60}


def test_share_project_emails_join_link(share_project, project, mailer, emailed_link, credentials):
    share_project(project["id"], EMAIL)

    [email] = mailer.sent
    assert email["to"] == EMAIL
    assert email["subject"] == f'{credentials["username"]} shared the project "{project["name"]}" with you'
    assert emailed_link().startswith("http://testserver/join?token=")
    assert "valid for 7 days" in email["body"]


def test_share_link_token_names_project_and_email(share_project, project, emailed_link):
    share_project(project["id"], EMAIL)

    assert read_share_token(token_of(emailed_link())) == (project["id"], EMAIL)


@pytest.mark.parametrize("base_url", ["https://pm.example.com", "https://pm.example.com/"])
def test_share_link_uses_public_base_url(share_project, project, emailed_link, monkeypatch, base_url):
    monkeypatch.setattr(project_routes, "PUBLIC_BASE_URL", base_url)

    share_project(project["id"], EMAIL)

    assert emailed_link().startswith("https://pm.example.com/join?token=")


def test_share_project_by_participant_is_forbidden(share_project, project, participant_auth, mailer):
    response = share_project(project["id"], EMAIL, auth=participant_auth)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the project owner can share it"
    assert mailer.sent == []


def test_share_project_by_non_member_is_not_found(share_project, project, other_auth, mailer):
    response = share_project(project["id"], EMAIL, auth=other_auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
    assert mailer.sent == []


def test_share_project_unknown_project_is_not_found(share_project, mailer):
    response = share_project(999, EMAIL)

    assert response.status_code == 404
    assert mailer.sent == []


@pytest.mark.parametrize(
    "email",
    [
        pytest.param(None, id="missing"),
        pytest.param("", id="empty"),
        pytest.param("not-an-email", id="no-at-sign"),
        pytest.param("bob@", id="no-domain"),
    ],
)
def test_share_project_invalid_email_is_rejected(share_project, project, mailer, email):
    response = share_project(project["id"], email)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "with"]
    assert mailer.sent == []


def test_share_project_mail_failure(share_project, project, mailer, monkeypatch):
    def fail(**email):
        raise MailDeliveryError("SES is down")

    monkeypatch.setattr(mailer, "send", fail)

    response = share_project(project["id"], EMAIL)

    assert response.status_code == 502
    assert response.json()["detail"] == "The email could not be sent"


def test_share_project_requires_authentication(share_project, project, bad_auth, mailer):
    response = share_project(project["id"], EMAIL, auth=bad_auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert mailer.sent == []


# --- share tokens ---------------------------------------------------------------------------------

def test_share_token_round_trip():
    assert read_share_token(create_share_token(42, EMAIL)) == (42, EMAIL)


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(lambda token: token[:-2] + ("AA" if not token.endswith("AA") else "BB"), id="changed-signature"),
        pytest.param(lambda token: token.replace(token.split(".")[0], "eyJwcm9qZWN0X2lkIjo5OX0"), id="changed-payload"),
        pytest.param(lambda token: "not-a-token", id="garbage"),
    ],
)
def test_tampered_share_token_is_invalid(tamper):
    with pytest.raises(InvalidShareTokenError):
        read_share_token(tamper(create_share_token(42, EMAIL)))


def test_share_token_from_another_secret_is_invalid(monkeypatch):
    monkeypatch.setattr(security, "SHARE_SECRET_KEY", "someone-elses-secret")
    foreign_token = create_share_token(42, EMAIL)
    monkeypatch.undo()

    with pytest.raises(InvalidShareTokenError):
        read_share_token(foreign_token)


def test_expired_share_token(monkeypatch):
    token = create_share_token(42, EMAIL)
    monkeypatch.setattr(security, "SHARE_LINK_MAX_AGE", -1)  # every token is now too old

    with pytest.raises(ExpiredShareTokenError):
        read_share_token(token)
