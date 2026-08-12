"""Watch a BookMyShow link and email when the wanted dates open up.

Configured entirely through environment variables so it can run from cron on a
server. See README.md for the full list.
"""

import argparse
import html as html_mod
import logging
import os
import sys
from datetime import datetime

from . import BmsError, __version__
from .client import ShowtimesClient
from .config import BmsConfigError, NotifierConfig
from .mailer import BmsMailError, build_message, send
from .parse import DayResult
from .render import Style, render_table
from .state import StateStore, fingerprint
from .url import build_url

log = logging.getLogger("bms-notify")


def watch_id(config: NotifierConfig) -> str:
    """Identifies this watch in the state file: one movie in one city."""
    return f"{config.target.event_code}-{config.target.city}"


def wanted_dates(config: NotifierConfig, client: ShowtimesClient) -> list[str]:
    """Which dates to check: the configured ones, or every date on offer."""
    if config.watch_any_date:
        return client.available_dates()
    return list(config.dates)


def collect(config: NotifierConfig, client: ShowtimesClient) -> list[DayResult]:
    """Fetch and filter every watched date that currently has shows."""
    hits: list[DayResult] = []
    for code in wanted_dates(config, client):
        day, _served = client.load(config.target, code)
        day = config.show_filter.apply(day)
        if day.show_count:
            hits.append(day)
        else:
            log.info("%s: no matching shows", code)
    return hits


def new_hits(
    config: NotifierConfig, store: StateStore, hits: list[DayResult]
) -> list[DayResult]:
    """Drop days already mailed about, unless their showtimes changed."""
    wid = watch_id(config)
    fresh = []
    for day in hits:
        digest = fingerprint(day)
        previous = store.seen(wid, day.date_code)
        if previous is None:
            fresh.append(day)
        elif previous != digest and config.notify_on_change:
            log.info("%s: showtimes changed since last mail", day.date_code)
            fresh.append(day)
        else:
            log.info("%s: already notified, skipping", day.date_code)
    return fresh


def _subject(config: NotifierConfig, days: list[DayResult]) -> str:
    labels = ", ".join(d.label or d.date_code for d in days)
    return f"{config.label}: tickets open for {labels}"


def render_body(config: NotifierConfig, days: list[DayResult]) -> tuple[str, str]:
    """Plain-text and HTML bodies for the notification mail."""
    plain = [
        f"{config.label} - {config.target.city_name}",
        "",
        render_table(days, Style(color=False)),
        "",
    ]
    rows = []
    for day in days:
        url = build_url(config.target, day.date_code)
        plain.append(f"Book {day.label or day.date_code}: {url}")
        rows.append(f'<h3><a href="{html_mod.escape(url)}">{html_mod.escape(day.label or day.date_code)}</a></h3>')
        for venue in day.venues:
            times = ", ".join(f"{s.time} ({s.status})" for s in venue.shows)
            rows.append(
                f"<p><b>{html_mod.escape(venue.name)}</b><br>{html_mod.escape(times)}</p>"
            )
    plain.append("")
    plain.append(f"checked at {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}")

    body = "\n".join(plain)
    html = (
        f"<html><body><h2>{html_mod.escape(config.label)} &mdash; "
        f"{html_mod.escape(config.target.city_name)}</h2>"
        + "".join(rows)
        + "</body></html>"
    )
    return body, html


def notify(config: NotifierConfig, days: list[DayResult]) -> None:
    """Send (or, in dry-run, print) the notification for these days."""
    body, html = render_body(config, days)
    subject = _subject(config, days)
    if config.dry_run or config.smtp is None:
        print(f"--- DRY RUN ---\nSubject: {subject}\n\n{body}")
        return
    msg = build_message(config.smtp, subject, body, html)
    send(config.smtp, msg)
    log.info("emailed %s", ", ".join(config.smtp.recipients))


def run(config: NotifierConfig) -> int:
    """One polling cycle. 0 = mail sent, 1 = nothing new, 2 = error."""
    store = StateStore(config.state_file)
    wid = watch_id(config)

    with ShowtimesClient() as client:
        # The first fetch primes the date strip, which "any date" mode needs.
        seed = config.dates[0] if config.dates else (
            config.target.date_code or datetime.now().strftime("%Y%m%d")
        )
        client.load(config.target, seed)
        hits = collect(config, client)

    fresh = new_hits(config, store, hits)
    if not fresh:
        log.info("nothing new to report")
        return 1

    notify(config, fresh)

    for day in fresh:
        store.record(wid, day.date_code, fingerprint(day))
    store.prune(wid, [d.date_code for d in hits])
    if not config.dry_run:
        store.save()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bms-notify",
        description="Email when a BookMyShow movie opens bookings on the dates you want. "
        "Configured via environment variables (see README).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the mail instead of sending it, and do not touch the state file",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="forget what was already notified for this movie before checking",
    )
    p.add_argument("--quiet", action="store_true", help="only log warnings and errors")
    p.add_argument("--version", action="version", version=f"bmstool {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.dry_run:
        # Set before parsing so incomplete SMTP settings don't block a dry run.
        os.environ["BMS_DRY_RUN"] = "1"

    try:
        config = NotifierConfig.from_env()
        if args.reset:
            store = StateStore(config.state_file)
            store.prune(watch_id(config), [])
            store.save()
            log.info("state reset for %s", watch_id(config))
        return run(config)
    except BmsConfigError as exc:
        log.error("configuration error: %s", exc)
        return 2
    except BmsMailError as exc:
        log.error("%s", exc)
        return 2
    except BmsError as exc:
        log.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
