"""Environment-driven configuration for the notifier."""

import os
import re
from dataclasses import dataclass
from datetime import datetime

from . import BmsError
from .filters import ShowFilter
from .url import BmsTarget, parse_url

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


class BmsConfigError(BmsError):
    """A required environment variable is missing or malformed."""


def _get(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _require(name: str) -> str:
    value = _get(name)
    if not value:
        raise BmsConfigError(f"{name} is required")
    return value


def _get_bool(name: str, default: bool = False) -> bool:
    raw = _get(name).lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise BmsConfigError(f"{name} must be a boolean (true/false), got {raw!r}")


def _get_int(name: str, default: int) -> int:
    raw = _get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise BmsConfigError(f"{name} must be an integer, got {raw!r}") from None


def _get_list(name: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,\n]", _get(name)) if p.strip()]


def normalize_date(value: str) -> str:
    """Accept YYYYMMDD or YYYY-MM-DD (or DD-MM-YYYY) and return YYYYMMDD."""
    raw = value.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise BmsConfigError(f"cannot parse date {value!r}; use YYYY-MM-DD or YYYYMMDD")


@dataclass
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    sender: str
    recipients: list[str]
    use_tls: bool = True       # STARTTLS on a plain connection
    use_ssl: bool = False      # implicit TLS (usually port 465)
    timeout: float = 30.0
    subject_prefix: str = "[BMS]"

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        recipients = _get_list("BMS_MAIL_TO")
        if not recipients:
            raise BmsConfigError("BMS_MAIL_TO is required (comma-separated addresses)")
        user = _get("BMS_SMTP_USER")
        port = _get_int("BMS_SMTP_PORT", 465 if _get_bool("BMS_SMTP_SSL") else 587)
        return cls(
            host=_require("BMS_SMTP_HOST"),
            port=port,
            user=user,
            password=_get("BMS_SMTP_PASSWORD"),
            sender=_get("BMS_MAIL_FROM") or user,
            recipients=recipients,
            use_tls=_get_bool("BMS_SMTP_STARTTLS", True),
            use_ssl=_get_bool("BMS_SMTP_SSL", port == 465),
            timeout=float(_get_int("BMS_SMTP_TIMEOUT", 30)),
            subject_prefix=_get("BMS_MAIL_SUBJECT_PREFIX", "[BMS]"),
        )


@dataclass
class NotifierConfig:
    target: BmsTarget
    dates: list[str]
    show_filter: ShowFilter
    smtp: SmtpConfig | None
    state_file: str
    notify_on_change: bool = True
    dry_run: bool = False
    watch_any_date: bool = False
    label: str = ""

    @classmethod
    def from_env(cls) -> "NotifierConfig":
        target = parse_url(_require("BMS_URL"))

        raw_dates = _get_list("BMS_DATES")
        watch_any = not raw_dates or any(d.lower() == "any" for d in raw_dates)
        dates = sorted(
            {normalize_date(d) for d in raw_dates if d.lower() != "any"}
        )

        dry_run = _get_bool("BMS_DRY_RUN")
        # In dry-run mode we print the mail instead of sending it, so incomplete
        # SMTP settings should not stop a config check.
        try:
            smtp = SmtpConfig.from_env()
        except BmsConfigError:
            if not dry_run:
                raise
            smtp = None

        default_state = os.path.join(
            os.path.expanduser("~"), ".cache", "bms-notify", "state.json"
        )
        return cls(
            target=target,
            dates=dates,
            show_filter=ShowFilter.build(
                venues=_get_list("BMS_VENUES"),
                after=_get("BMS_AFTER") or None,
                before=_get("BMS_BEFORE") or None,
                available_only=_get_bool("BMS_AVAILABLE_ONLY", True),
            ),
            smtp=smtp,
            state_file=_get("BMS_STATE_FILE") or default_state,
            notify_on_change=_get_bool("BMS_NOTIFY_ON_CHANGE", True),
            dry_run=dry_run,
            watch_any_date=watch_any,
            label=_get("BMS_LABEL") or target.title,
        )
