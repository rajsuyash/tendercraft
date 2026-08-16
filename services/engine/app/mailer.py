"""Sending an email. One module, plain SMTP, no vendor.

**Why SMTP and not a transactional-email API.** The workspace already pays for email hosting on
the domain this bot advertises as its contact address, and every provider worth using speaks
SMTP. A hosted API would be a new subscription, a new key to rotate and a new outage surface,
to send a handful of digests to colleagues who asked for them. If volume ever justifies a
provider, the swap is four environment variables and no code.

**Configuration is optional, but a configured-and-broken state is loud.** Alerts are a feature a
workspace opts into, so an unset `SMTP_HOST` is not a startup failure — the engine runs fine
without it and `is_configured()` reports false. But once someone has switched alerts ON, a
missing credential must raise a NAMED error rather than quietly succeed: a notification system
that reports "sent" and delivers nothing is worse than one that is plainly off, because the
person waiting on it has no reason to check.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger(__name__)

#: Implicit TLS. 587/STARTTLS is supported by reading the port — see `_send`.
_DEFAULT_PORT = 465


class MailNotConfigured(RuntimeError):
    """Alerts are on, but this deployment cannot send. Named, never swallowed."""


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    from_addr: str
    from_name: str

    @property
    def sender(self) -> str:
        return formataddr((self.from_name, self.from_addr))


def load_config() -> SmtpConfig | None:
    """Read SMTP settings from the environment. None when the deployment has none."""
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    if not (host and user and password):
        return None
    return SmtpConfig(
        host=host,
        port=int(os.environ.get("SMTP_PORT", _DEFAULT_PORT)),
        user=user,
        password=password,
        # Defaults to the authenticating user, which is what every host expects and what
        # keeps SPF/DKIM alignment intact. Overriding it with an unaligned address is the
        # standard way to land in spam.
        from_addr=os.environ.get("SMTP_FROM", "").strip() or user,
        from_name=os.environ.get("SMTP_FROM_NAME", "TenderCraft").strip(),
    )


def is_configured() -> bool:
    return load_config() is not None


def _send(config: SmtpConfig, message: EmailMessage) -> None:
    context = ssl.create_default_context()
    if config.port == 587:
        with smtplib.SMTP(config.host, config.port, timeout=20) as server:
            server.starttls(context=context)
            server.login(config.user, config.password)
            server.send_message(message)
        return
    with smtplib.SMTP_SSL(config.host, config.port, timeout=20, context=context) as server:
        server.login(config.user, config.password)
        server.send_message(message)


def send(to: str, subject: str, body: str) -> None:
    """Send one plain-text email. Raises `MailNotConfigured` if this deployment cannot.

    Plain text on purpose. These messages are read on a phone at 7am and forwarded to a
    colleague; HTML buys nothing and costs deliverability.
    """
    config = load_config()
    if config is None:
        raise MailNotConfigured(
            "alerts are enabled but SMTP is not configured — set SMTP_HOST, SMTP_USER and "
            "SMTP_PASSWORD"
        )
    message = EmailMessage()
    message["From"] = config.sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    _send(config, message)
    # The address is logged, the body is not: a digest names which tenders a workspace is
    # pursuing, which is exactly the thing that must not sit in a shared log.
    log.info("notification sent to %s (%s)", to, subject[:60])
