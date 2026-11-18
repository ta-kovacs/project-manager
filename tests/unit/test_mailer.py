"""Sending emails: the SES backend, the console backend and choosing between them."""

import logging

import boto3
import pytest
from botocore.stub import Stubber

import app.mailer as mailer_module
from app.mailer import ConsoleMailer, MailDeliveryError, SesMailer

SENDER = "Project Manager <no-reply@example.com>"


@pytest.fixture
def ses_client(monkeypatch):
    """A real boto3 SESv2 client whose requests are intercepted by `Stubber` (nothing reaches AWS)."""
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "testing")
    client = boto3.client("sesv2", region_name="eu-north-1")
    with Stubber(client) as stubber:
        client.stubber = stubber
        yield client
        stubber.assert_no_pending_responses()


def test_ses_mailer_sends_plain_text_email(ses_client):
    ses_client.stubber.add_response(
        "send_email",
        {"MessageId": "msg-1"},
        expected_params={
            "FromEmailAddress": SENDER,
            "Destination": {"ToAddresses": ["bob@example.com"]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": "Join Apollo", "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": "Open this link", "Charset": "UTF-8"}},
                }
            },
        },
    )

    SesMailer(SENDER, client=ses_client).send("bob@example.com", "Join Apollo", "Open this link")


def test_ses_mailer_failure_raises_mail_delivery_error(ses_client):
    ses_client.stubber.add_client_error(
        "send_email", service_error_code="MessageRejected", service_message="Email address is not verified."
    )

    with pytest.raises(MailDeliveryError, match="not verified"):
        SesMailer(SENDER, client=ses_client).send("bob@example.com", "Subject", "Body")


def test_ses_mailer_without_region_raises_mail_delivery_error(monkeypatch, tmp_path):
    for name in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        monkeypatch.delenv(name, raising=False)
    # No ~/.aws/config either, so boto3 finds no region at all.
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "missing-config"))
    mailer = SesMailer(SENDER)  # creating the mailer doesn't need AWS yet

    with pytest.raises(MailDeliveryError, match="region"):
        mailer.send("bob@example.com", "Subject", "Body")


def test_console_mailer_logs_email(caplog):
    with caplog.at_level(logging.WARNING, logger="app.mailer"):
        ConsoleMailer().send("bob@example.com", "Join Apollo", "Open this link")

    assert "To: bob@example.com" in caplog.text
    assert "Subject: Join Apollo" in caplog.text
    assert "Open this link" in caplog.text


# --- choosing the backend (get_mailer) ------------------------------------------------------------


@pytest.fixture
def configure_mailer(monkeypatch):
    """Set the mail settings get_mailer reads, with a fresh cache before and after."""

    def _configure(backend, sender=None):
        monkeypatch.setattr(mailer_module, "MAIL_BACKEND", backend)
        monkeypatch.setattr(mailer_module, "MAIL_SENDER", sender)
        mailer_module.get_mailer.cache_clear()

    yield _configure
    mailer_module.get_mailer.cache_clear()


def test_get_mailer_console(configure_mailer):
    configure_mailer("console")

    assert isinstance(mailer_module.get_mailer(), ConsoleMailer)


def test_get_mailer_ses(configure_mailer, monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    configure_mailer("ses", sender=SENDER)

    mailer = mailer_module.get_mailer()

    assert isinstance(mailer, SesMailer)
    assert mailer.sender == SENDER


@pytest.mark.parametrize(
    ("backend", "message"),
    [
        pytest.param("ses", "MAIL_SENDER is not set", id="ses-without-sender"),
        pytest.param("smtp", "Unknown MAIL_BACKEND 'smtp'", id="unknown-backend"),
    ],
)
def test_get_mailer_misconfiguration_fails(configure_mailer, backend, message):
    configure_mailer(backend)

    with pytest.raises(RuntimeError, match=message):
        mailer_module.get_mailer()
