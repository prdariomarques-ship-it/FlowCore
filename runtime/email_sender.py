"""FlowCore — outbound email via plain SMTP.

Distinct from runtime/outlook.py's Microsoft Graph integration, which is
explicitly read-only (Mail.Read scope only, "No sending" per its own
docstring) — extending that integration's scope to send mail is a real,
separate decision (a new OAuth consent) that hasn't been asked for here.
SMTP is the simplest robust option that works with any provider (Gmail
app password, a corporate relay, SendGrid/SES SMTP relay, ...) without
requiring a new OAuth flow, and needs no new dependency (`smtplib`,
`email.mime` are stdlib).

Configuration lives in ~/.flowcore/email.json, same two-tier convention
as ai.json (api/dashboard_routes.py's _read_json):
    {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "username": "advisor@example.com",
        "password": "an app password, not the account password",
        "from_address": "advisor@example.com",
        "from_name": "FlowCore Wealth Copilot",
        "use_tls": true
    }
Never configured out of the box — is_configured() lets callers degrade
honestly ("email não configurado") instead of pretending to send.
"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path.home() / ".flowcore" / "email.json"


class EmailError(RuntimeError):
    """Base class for all email-sending errors raised by FlowCore."""


class EmailNotConfiguredError(EmailError):
    """~/.flowcore/email.json is missing or incomplete."""


def _load_config() -> dict[str, Any] | None:
    try:
        if not _CONFIG_PATH.exists():
            return None
        import json

        cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    required = ("smtp_host", "smtp_port", "username", "password", "from_address")
    if not all(cfg.get(k) for k in required):
        return None
    return cfg


def is_configured() -> bool:
    return _load_config() is not None


def send_email(to_address: str, subject: str, body: str) -> dict[str, Any]:
    """Send a plain-text email via the configured SMTP relay.

    Raises EmailNotConfiguredError if ~/.flowcore/email.json is missing
    or incomplete, EmailError on any SMTP-level failure. Never silently
    "succeeds" without actually attempting delivery.
    """
    cfg = _load_config()
    if cfg is None:
        raise EmailNotConfiguredError(
            "Email não configurado. Crie ~/.flowcore/email.json com smtp_host, smtp_port, "
            "username, password e from_address."
        )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg.get("from_name", ""), cfg["from_address"]))
    msg["To"] = to_address

    try:
        with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"]), timeout=15) as server:
            if cfg.get("use_tls", True):
                server.starttls()
            server.login(cfg["username"], cfg["password"])
            server.sendmail(cfg["from_address"], [to_address], msg.as_string())
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"Falha ao enviar email via {cfg['smtp_host']}: {e}") from e

    return {"to": to_address, "subject": subject}
