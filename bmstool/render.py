"""Output formatting: table, compact and json."""

import dataclasses
import json

from .parse import (
    ALMOST_FULL,
    AVAILABLE,
    DateOption,
    DayResult,
    FILLING_FAST,
    SOLD_OUT,
)

_COLORS = {
    AVAILABLE: "\033[32m",
    FILLING_FAST: "\033[33m",
    ALMOST_FULL: "\033[31m",
    SOLD_OUT: "\033[90m",
}
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

_MARKS = {
    AVAILABLE: " ",
    FILLING_FAST: "~",
    ALMOST_FULL: "!",
    SOLD_OUT: "x",
}

LEGEND = "legend:  available   ~ filling fast   ! almost full   x sold out"


class Style:
    def __init__(self, color: bool):
        self.color = color

    def paint(self, text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if self.color else text

    def status(self, text: str, status: str) -> str:
        return self.paint(text, _COLORS.get(status, ""))

    def bold(self, text: str) -> str:
        return self.paint(text, _BOLD)

    def dim(self, text: str) -> str:
        return self.paint(text, _DIM)


def render_dates(dates: list[DateOption], style: Style) -> str:
    lines = [style.bold("Dates")]
    for d in dates:
        if d.available:
            lines.append(f"  {style.status('*', AVAILABLE)} {d.iso}  {d.label}")
        else:
            lines.append(style.dim(f"  - {d.iso}  {d.label}  (no shows)"))
    return "\n".join(lines)


def render_table(days: list[DayResult], style: Style) -> str:
    out: list[str] = []
    for day in days:
        out.append("")
        out.append(style.bold(f"{day.label}  ({day.date_code})"))
        if not day.venues:
            out.append("  no shows")
            continue
        for venue in day.venues:
            out.append(f"  {style.bold(venue.name)}")
            if venue.info:
                out.append(style.dim("    " + " | ".join(venue.info)))
            for show in venue.shows:
                mark = _MARKS.get(show.status, "?")
                cell = style.status(f"{mark} {show.time:>8}", show.status)
                bits = [b for b in (show.show_format, show.price_range) if b]
                suffix = style.dim("   " + "   ".join(bits)) if bits else ""
                out.append(f"    {cell}{suffix}")
    out.append("")
    out.append(style.dim(LEGEND))
    return "\n".join(out).lstrip("\n")


def render_compact(days: list[DayResult], style: Style) -> str:
    out: list[str] = []
    for day in days:
        if not day.venues:
            out.append(f"{day.date_code}  no shows")
            continue
        for venue in day.venues:
            times = " ".join(
                style.status(f"{_MARKS.get(s.status, '?')}{s.time}", s.status)
                for s in venue.shows
            )
            out.append(f"{day.date_code}  {venue.name}: {times}")
    return "\n".join(out)


def render_json(days: list[DayResult], dates: list[DateOption]) -> str:
    payload = {
        "dates": [dataclasses.asdict(d) | {"iso": d.iso, "label": d.label} for d in dates],
        "days": [dataclasses.asdict(d) for d in days],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
