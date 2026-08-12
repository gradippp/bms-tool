"""Sending notification mail over SMTP with credentials from the environment."""

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from . import BmsError
from .config import SmtpConfig


class BmsMailError(BmsError):
    """The notification could not be sent."""


def build_message(smtp: SmtpConfig, subject: str, body: str, html: str = "") -> EmailMessage:
    msg = EmailMessage()
    prefix = f"{smtp.subject_prefix} " if smtp.subject_prefix else ""
    msg["Subject"] = f"{prefix}{subject}"
    msg["From"] = smtp.sender
    msg["To"] = ", ".join(smtp.recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="bms-notify")
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def send(smtp: SmtpConfig, msg: EmailMessage) -> None:
    """Deliver a message, raising BmsMailError on any SMTP failure."""
    context = ssl.create_default_context()
    try:
        if smtp.use_ssl:
            server = smtplib.SMTP_SSL(
                smtp.host, smtp.port, timeout=smtp.timeout, context=context
            )
        else:
            server = smtplib.SMTP(smtp.host, smtp.port, timeout=smtp.timeout)
        with server:
            server.ehlo()
            if not smtp.use_ssl and smtp.use_tls:
                server.starttls(context=context)
                server.ehlo()
            if smtp.user and smtp.password:
                server.login(smtp.user, smtp.password)
            server.send_message(msg, from_addr=smtp.sender, to_addrs=smtp.recipients)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        raise BmsMailError(f"SMTP delivery to {smtp.host}:{smtp.port} failed: {exc}") from exc
