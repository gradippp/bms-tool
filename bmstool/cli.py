"""Command line entrypoint."""

import argparse
import os
import sys
from datetime import datetime, timedelta

from . import BmsError, __version__
from .client import ShowtimesClient
from .filters import ShowFilter
from .parse import DateOption, DayResult
from .render import Style, render_compact, render_dates, render_json, render_table
from .url import parse_url


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bms",
        description="List the days and showtimes available for a BookMyShow movie link.",
        epilog='example: bms "https://in.bookmyshow.com/movies/mumbai/'
        'some-movie/buytickets/ET00000000/20260101"',
    )
    p.add_argument("url", help="BookMyShow buytickets URL")
    p.add_argument(
        "--date",
        action="append",
        metavar="YYYYMMDD",
        help="fetch a specific date (repeatable); overrides --days",
    )
    p.add_argument(
        "--days",
        type=int,
        metavar="N",
        help="fetch the next N days starting from the URL's date, "
        "regardless of what the date strip says",
    )
    p.add_argument(
        "--dates-only",
        action="store_true",
        help="only list which days have shows; skip per-cinema fetches",
    )
    p.add_argument(
        "--venue",
        action="append",
        metavar="TEXT",
        help="only cinemas whose name contains TEXT (repeatable, case-insensitive)",
    )
    p.add_argument("--after", metavar="HH:MM", help="only shows at or after this time")
    p.add_argument("--before", metavar="HH:MM", help="only shows at or before this time")
    p.add_argument(
        "--available-only", action="store_true", help="hide sold-out shows"
    )
    p.add_argument(
        "--format",
        choices=("table", "compact", "json"),
        default="table",
        help="output format (default: table)",
    )
    p.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    p.add_argument("--version", action="version", version=f"bmstool {__version__}")
    return p


def _next_dates(start: str, count: int) -> list[str]:
    try:
        day = datetime.strptime(start, "%Y%m%d")
    except ValueError:
        raise SystemExit(f"invalid date code: {start!r}")
    return [(day + timedelta(days=i)).strftime("%Y%m%d") for i in range(max(1, count))]


def _use_color(args) -> bool:
    if args.no_color or args.format == "json" or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    style = Style(_use_color(args))

    try:
        target = parse_url(args.url)
        show_filter = ShowFilter.build(
            venues=args.venue,
            after=args.after,
            before=args.before,
            available_only=args.available_only,
        )
    except BmsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        with ShowtimesClient() as client:
            first_code = target.date_code or datetime.now().strftime("%Y%m%d")
            first_day, _served = client.load(target, first_code)
            dates: list[DateOption] = client.dates
            cached = {first_code: first_day}

            if args.date:
                wanted = list(dict.fromkeys(args.date))
            elif args.days:
                wanted = _next_dates(first_code, args.days)
            else:
                wanted = client.available_dates() or [first_code]

            if args.dates_only:
                if args.format == "json":
                    print(render_json([], dates))
                else:
                    print(render_dates(dates, style))
                return 0 if any(d.available for d in dates) else 1

            days: list[DayResult] = []
            for code in wanted:
                day = cached.get(code) or client.load(target, code)[0]
                days.append(show_filter.apply(day))
    except BmsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130

    if args.format == "json":
        print(render_json(days, dates))
    elif args.format == "compact":
        print(render_compact(days, style))
    else:
        header = f"{target.title} - {target.city_name}"
        print(style.bold(header))
        print(render_table(days, style))

    return 0 if any(d.show_count for d in days) else 1


if __name__ == "__main__":
    sys.exit(main())
