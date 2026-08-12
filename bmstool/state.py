"""Persistent state so the notifier does not mail the same news twice."""

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone

from .parse import DayResult


def fingerprint(day: DayResult) -> str:
    """Stable hash of a day's cinemas, times and availability."""
    parts = [
        f"{venue.code}|{venue.name}|"
        + ",".join(f"{s.time_code}:{s.status}" for s in venue.shows)
        for venue in sorted(day.venues, key=lambda v: (v.code, v.name))
    ]
    blob = ";".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


class StateStore:
    """A tiny JSON file keyed by watch id -> {date_code: fingerprint}."""

    def __init__(self, path: str):
        self.path = path
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            self._data = loaded if isinstance(loaded, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            # A missing or corrupt state file just means "notify as if new".
            self._data = {}

    def seen(self, watch_id: str, date_code: str) -> str | None:
        """The fingerprint last notified for this date, if any."""
        return (self._data.get("watches", {}).get(watch_id, {}) or {}).get(date_code)

    def record(self, watch_id: str, date_code: str, digest: str) -> None:
        watches = self._data.setdefault("watches", {})
        watches.setdefault(watch_id, {})[date_code] = digest

    def prune(self, watch_id: str, keep: list[str]) -> None:
        """Drop dates that are no longer being watched (e.g. past dates)."""
        watch = self._data.get("watches", {}).get(watch_id)
        if watch:
            for code in list(watch):
                if code not in keep:
                    del watch[code]

    def save(self) -> None:
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".state-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
