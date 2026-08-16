"""Sending an email. Two transports, one interface, no new subscription either way.

**Resend when a key is present, SMTP otherwise.** Both are free at this volume — the account
already holds a Resend key, and the domain already has email hosting — so the choice is about
reliability rather than cost. Resend leads because this runs on Cloud Run: an HTTPS POST needs
no long-lived connection, survives a scale-to-zero container, cannot be tripped by a blocked
SMTP egress port, and returns a readable JSON error instead of a three-digit SMTP code. SMTP
stays because it is the escape hatch that owes nothing to any vendor, and because a workspace
that would rather send from its own mail server can.

**Configuration is optional, but a configured-and-broken state is loud.** Alerts are a feature a
workspace opts into, so no key at all is not a startup failure — the engine runs fine and
`is_configured()` reports false. But once someone has switched alerts ON, a missing credential
must raise a NAMED error rather than quietly succeed: a notification system that reports "sent"
and delivers nothing is worse than one that is plainly off, because the person waiting on it
has no reason to check.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from . import http

log = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"

#: Resend's shared sender. It needs no DNS and works on day one, but it will only deliver to
#: the Resend account owner's own address — which makes it exactly right for a smoke test and
#: exactly wrong for a customer digest. Set RESEND_FROM to an address on a verified domain
#: before anyone else is on the recipient list.
_RESEND_TEST_FROM = "onboarding@resend.dev"

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


def _resend_key() -> str:
    return os.environ.get("RESEND_API_KEY", "").strip()


def _resend_from() -> str:
    addr = os.environ.get("RESEND_FROM", "").strip() or _RESEND_TEST_FROM
    name = os.environ.get("SMTP_FROM_NAME", "TenderCraft").strip()
    return formataddr((name, addr)) if "<" not in addr else addr


def is_configured() -> bool:
    """Can this deployment send at all, by either route?"""
    return bool(_resend_key()) or load_config() is not None


def transport() -> str:
    """Which route a send would take. Surfaced so a settings screen can say so."""
    if _resend_key():
        return "resend"
    return "smtp" if load_config() else "none"


def _send_via_resend(to: str, subject: str, body: str) -> None:
    """POST one email. Uses the shared httpx client — a per-call client would pay a fresh TLS
    handshake every time, which is the exact cost docs/known-pitfalls.md measured elsewhere."""
    try:
        r = http.client.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {_resend_key()}",
                     "Content-Type": "application/json"},
            json={"from": _resend_from(), "to": [to], "subject": subject, "text": body},
            timeout=20,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # Resend's body says WHY (unverified domain, invalid recipient, rate limit). Losing it
        # to a bare status code turns a five-second fix into an afternoon.
        detail = exc.response.text[:300]
        raise RuntimeError(f"resend rejected the message ({exc.response.status_code}): "
                           f"{detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"resend unreachable: {exc}") from exc


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
    if _resend_key():
        _send_via_resend(to, subject, body)
        log.info("notification sent to %s via resend (%s)", to, subject[:60])
        return

    config = load_config()
    if config is None:
        raise MailNotConfigured(
            "alerts are enabled but this deployment cannot send — set RESEND_API_KEY, or "
            "SMTP_HOST, SMTP_USER and SMTP_PASSWORD"
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
