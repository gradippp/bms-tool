"""HTTP fetching of BookMyShow showtime pages."""

import os
import time

import requests

from . import BmsFetchError
from .url import BmsTarget, build_url

try:  # optional: TLS impersonation, needed to get past Cloudflare
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - falls back to plain requests
    curl_requests = None

# Cloudflare fingerprints the TLS handshake, not the headers: stock `requests`
# is answered with a 403 block page on every attempt regardless of User-Agent.
# curl_cffi replays a real browser's handshake instead. The Chrome profiles are
# currently blocked too, so this defaults to Safari; override if that flips.
IMPERSONATE = os.environ.get("BMS_IMPERSONATE", "safari17_0")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://in.bookmyshow.com/",
    "Upgrade-Insecure-Requests": "1",
}


class Fetcher:
    """Reusable session for fetching showtime pages, with retry and polite delay."""

    def __init__(self, timeout: float = 20.0, retries: int = 3, delay: float = 0.5):
        if curl_requests is not None:
            self.session = curl_requests.Session(impersonate=IMPERSONATE)
        else:
            self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout
        self.retries = max(1, retries)
        self.delay = delay
        self._fetched_any = False

    def fetch_page(self, target: BmsTarget, date_code: str | None = None) -> str:
        url = build_url(target, date_code)
        if self._fetched_any and self.delay:
            time.sleep(self.delay)
        self._fetched_any = True

        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except Exception as exc:  # curl_cffi and requests raise unrelated types
                last_error = exc
            else:
                if resp.status_code == 200:
                    return resp.text
                last_error = BmsFetchError(
                    f"HTTP {resp.status_code} for {url}"
                )
                if resp.status_code in (400, 404):
                    break
            if attempt + 1 < self.retries:
                # Back off: a 403 here is a bot check, and hammering it sticks.
                time.sleep(1.0 * 2**attempt)
        raise BmsFetchError(f"Could not fetch {url}: {last_error}")

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
