"""Parsing and rebuilding BookMyShow buytickets URLs."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from . import BmsUrlError

_PATH_RE = re.compile(
    r"^/movies/(?P<city>[^/]+)/(?P<slug>[^/]+)/buytickets/(?P<event>ET\d+)"
    r"(?:/(?P<date>\d{8}))?/?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BmsTarget:
    scheme: str
    host: str
    city: str
    slug: str
    event_code: str
    date_code: str | None
    query: str

    @property
    def title(self) -> str:
        return self.slug.replace("-", " ").title()

    @property
    def city_name(self) -> str:
        return self.city.replace("-", " ").title()


def parse_url(url: str) -> BmsTarget:
    """Parse a BMS buytickets URL into its parts."""
    parts = urlsplit(url.strip())
    if not parts.netloc:
        raise BmsUrlError(f"Not a URL: {url!r}")
    if "bookmyshow.com" not in parts.netloc.lower():
        raise BmsUrlError(f"Not a bookmyshow.com URL: {parts.netloc}")
    m = _PATH_RE.match(parts.path)
    if not m:
        raise BmsUrlError(
            "URL must look like "
            "https://in.bookmyshow.com/movies/<city>/<movie>/buytickets/<ETcode>/<YYYYMMDD>"
        )
    return BmsTarget(
        scheme=parts.scheme or "https",
        host=parts.netloc,
        city=m.group("city"),
        slug=m.group("slug"),
        event_code=m.group("event").upper(),
        date_code=m.group("date"),
        query=parts.query,
    )


def build_url(target: BmsTarget, date_code: str | None = None) -> str:
    """Rebuild the URL for a (possibly different) date, keeping the query string."""
    date_code = date_code or target.date_code
    path = f"/movies/{target.city}/{target.slug}/buytickets/{target.event_code}"
    if date_code:
        path += f"/{date_code}"
    return urlunsplit((target.scheme, target.host, path, target.query, ""))
