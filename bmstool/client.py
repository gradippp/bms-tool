"""High-level access to BookMyShow showtimes, shared by the CLI and the notifier."""

from .extract import extract_initial_state, find_showtimes_payload
from .fetch import Fetcher
from .parse import DateOption, DayResult, parse_dates, parse_day, selected_date_code
from .url import BmsTarget


class ShowtimesClient:
    """Fetches and parses showtime pages, reusing one HTTP session."""

    def __init__(self, fetcher: Fetcher | None = None):
        self.fetcher = fetcher or Fetcher()
        self._dates: list[DateOption] = []

    @property
    def dates(self) -> list[DateOption]:
        """The date strip from the most recent fetch."""
        return self._dates

    def load(self, target: BmsTarget, date_code: str) -> tuple[DayResult, str]:
        """Fetch one date.

        Returns the parsed day and the date BookMyShow actually served -- it
        silently falls back to the nearest date with shows when the requested
        day has none, so callers must compare the two.
        """
        html = self.fetcher.fetch_page(target, date_code)
        payload = find_showtimes_payload(extract_initial_state(html))
        self._dates = parse_dates(payload)
        served = selected_date_code(self._dates) or date_code
        if served != date_code:
            return parse_day({}, date_code, self._dates), served
        return parse_day(payload, date_code, self._dates), served

    def available_dates(self) -> list[str]:
        return [d.date_code for d in self._dates if d.available]

    def close(self) -> None:
        self.fetcher.close()

    def __enter__(self) -> "ShowtimesClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
