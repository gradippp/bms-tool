"""Show filtering shared by the CLI and the notifier."""

from dataclasses import dataclass, field

from . import BmsError
from .parse import SOLD_OUT, DayResult


class BmsFilterError(BmsError):
    """A filter value could not be understood."""


def parse_hhmm(value: str | None, label: str) -> int | None:
    """'18:30' -> minutes since midnight. None passes through."""
    if value is None or value == "":
        return None
    try:
        hour, minute = str(value).split(":")
        hour, minute = int(hour), int(minute)
    except ValueError:
        raise BmsFilterError(f"{label} must be HH:MM, got {value!r}") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise BmsFilterError(f"{label} is not a valid time: {value!r}")
    return hour * 60 + minute


@dataclass
class ShowFilter:
    venues: list[str] = field(default_factory=list)
    after: int | None = None
    before: int | None = None
    available_only: bool = False

    @classmethod
    def build(
        cls,
        venues: list[str] | None = None,
        after: str | None = None,
        before: str | None = None,
        available_only: bool = False,
    ) -> "ShowFilter":
        return cls(
            venues=[v.lower() for v in (venues or []) if v],
            after=parse_hhmm(after, "after"),
            before=parse_hhmm(before, "before"),
            available_only=available_only,
        )

    def keeps_venue(self, name: str) -> bool:
        return not self.venues or any(n in name.lower() for n in self.venues)

    def keeps_show(self, show) -> bool:
        if self.available_only and show.status == SOLD_OUT:
            return False
        if self.after is not None and show.minutes < self.after:
            return False
        if self.before is not None and show.minutes > self.before:
            return False
        return True

    def apply(self, day: DayResult) -> DayResult:
        """Filter a day in place and return it. Venues with no surviving shows drop."""
        kept = []
        for venue in day.venues:
            if not self.keeps_venue(venue.name):
                continue
            shows = [s for s in venue.shows if self.keeps_show(s)]
            if shows:
                venue.shows = shows
                kept.append(venue)
        day.venues = kept
        return day
