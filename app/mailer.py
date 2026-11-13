"""How emails are sent.

Deployed environments use AWS SES; locally emails are written to the log. Routes only depend on
`get_mailer`, so they work the same with either backend.
"""

import logging
from functools import lru_cache
from typing import Protocol

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import MAIL_BACKEND, MAIL_SENDER

logger = logging.getLogger(__name__)


class MailDeliveryError(Exception):
    """The email could not be handed over for delivery."""


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None:
        """Send a plain-text email; raises MailDeliveryError if it can't be sent."""
        ...


class ConsoleMailer:
    """Writes each email to the application log instead of sending it."""

    def send(self, to: str, subject: str, body: str) -> None:
        logger.warning("Email (not sent, MAIL_BACKEND=console)\nTo: %s\nSubject: %s\n\n%s", to, subject, body)


class SesMailer:
    """Sends emails through AWS SES (v2 API) from a verified sender identity."""

    def __init__(self, sender: str, client=None):
        self.sender = sender
        self.client = client or boto3.client("sesv2")

    def send(self, to: str, subject: str, body: str) -> None:
        try:
            self.client.send_email(
                FromEmailAddress=self.sender,
                Destination={"ToAddresses": [to]},
                Content={
                    "Simple": {
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                    }
                },
            )
        except (ClientError, BotoCoreError) as error:
            logger.exception("SES could not send an email to %s", to)
            raise MailDeliveryError(str(error)) from error


@lru_cache
def get_mailer() -> Mailer:
    """The configured mailer (created once and reused)."""
    if MAIL_BACKEND == "ses":
        if not MAIL_SENDER:
            raise RuntimeError("MAIL_BACKEND is 'ses' but MAIL_SENDER is not set")
        return SesMailer(MAIL_SENDER)
    if MAIL_BACKEND == "console":
        return ConsoleMailer()
    raise RuntimeError(f"Unknown MAIL_BACKEND {MAIL_BACKEND!r} (expected 'ses' or 'console')")
