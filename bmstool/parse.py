"""Turning the raw BookMyShow payload into plain dataclasses."""

from dataclasses import dataclass, field
from datetime import datetime

AVAILABLE = "available"
FILLING_FAST = "filling fast"
ALMOST_FULL = "almost full"
SOLD_OUT = "sold out"
UNKNOWN = "unknown"

_STATUS_ORDER = [SOLD_OUT, ALMOST_FULL, FILLING_FAST, AVAILABLE]


@dataclass
class DateOption:
    date_code: str
    weekday: str
    day: str
    month: str
    available: bool
    selected: bool

    @property
    def label(self) -> str:
        return f"{self.weekday} {self.day} {self.month}".strip()

    @property
    def iso(self) -> str:
        try:
            return datetime.strptime(self.date_code, "%Y%m%d").date().isoformat()
        except ValueError:
            return self.date_code


@dataclass
class SeatCategory:
    name: str
    price: str
    status: str


@dataclass
class Show:
    time: str
    time_code: str
    session_id: str
    status: str
    show_format: str
    categories: list[SeatCategory] = field(default_factory=list)

    @property
    def minutes(self) -> int:
        """Minutes since midnight, for sorting and --after/--before filters."""
        code = (self.time_code or "").zfill(4)
        try:
            return int(code[:2]) * 60 + int(code[2:])
        except ValueError:
            return 0

    @property
    def price_range(self) -> str:
        values = []
        for cat in self.categories:
            digits = "".join(c for c in cat.price if c.isdigit() or c == ".")
            try:
                values.append(float(digits))
            except ValueError:
                continue
        if not values:
            return ""
        lo, hi = min(values), max(values)
        if lo == hi:
            return f"Rs.{lo:.0f}"
        return f"Rs.{lo:.0f}-{hi:.0f}"


@dataclass
class Venue:
    name: str
    code: str
    info: list[str] = field(default_factory=list)
    url: str = ""
    shows: list[Show] = field(default_factory=list)


@dataclass
class DayResult:
    date_code: str
    label: str
    venues: list[Venue] = field(default_factory=list)

    @property
    def show_count(self) -> int:
        return sum(len(v.shows) for v in self.venues)


def _texts(node: dict) -> list[str]:
    return [t.get("text", "") for t in node.get("data") or [] if isinstance(t, dict)]


def parse_dates(payload: dict) -> list[DateOption]:
    """Read the date strip: which days this movie is showing."""
    dates: list[DateOption] = []
    for widget in payload.get("topStickyWidgets") or []:
        if not isinstance(widget, dict) or widget.get("type") != "horizontal-block-list":
            continue
        for item in widget.get("data") or []:
            if not isinstance(item, dict) or item.get("type") != "vertical-text-list":
                continue
            date_code = str(item.get("id") or "")
            if len(date_code) != 8 or not date_code.isdigit():
                continue
            style = str(item.get("styleId") or "")
            parts = _texts(item)
            selected = "selected" in style
            dates.append(
                DateOption(
                    date_code=date_code,
                    weekday=parts[0] if len(parts) > 0 else "",
                    day=parts[1] if len(parts) > 1 else "",
                    month=parts[2] if len(parts) > 2 else "",
                    available=selected or "disabled" not in style or "cta" in item,
                    selected=selected,
                )
            )
        if dates:
            break
    return dates


def selected_date_code(dates: list[DateOption]) -> str:
    """The date the server actually rendered (it silently falls back to the nearest
    date with shows when you request a day that has none)."""
    return next((d.date_code for d in dates if d.selected), "")


def _parse_bottomsheet(show: dict) -> tuple[str, list[SeatCategory]]:
    """Pull format string and seat categories out of the double-tap bottom sheet."""
    gesture = show.get("customGestureCTA") or {}
    sheet = ((gesture.get("additionalData") or {}).get("bottomSheetData") or {})
    show_format = ""
    categories: list[SeatCategory] = []
    for widget in sheet.get("widgets") or []:
        if not isinstance(widget, dict):
            continue
        var = widget.get("variableData") or {}
        layout = str(widget.get("layoutId") or "")
        if layout == "format-container":
            show_format = str(var.get("format") or "")
        elif layout.startswith("seat-category-type-"):
            categories.append(
                SeatCategory(
                    name=str(var.get("seatType") or ""),
                    price=str(var.get("seatCost") or ""),
                    status=str(var.get("seatAvalibility") or "").strip().lower()
                    or UNKNOWN,
                )
            )
    return show_format, categories


def _status_from(categories: list[SeatCategory], style_id: str) -> str:
    """Best available status: seat categories first, pill colour as fallback."""
    statuses = {c.status for c in categories}
    for status in (AVAILABLE, FILLING_FAST, ALMOST_FULL):
        if status in statuses:
            return status
    if statuses and statuses <= {SOLD_OUT}:
        return SOLD_OUT

    style = style_id.lower()
    if "sold" in style or "grey" in style or "gray" in style:
        return SOLD_OUT
    if "orange" in style:
        return FILLING_FAST
    if "red" in style:
        return ALMOST_FULL
    if "green" in style:
        return AVAILABLE
    return UNKNOWN


def _parse_show(raw: dict) -> Show | None:
    extra = raw.get("additionalData") or {}
    time_text = str(raw.get("title") or extra.get("showTime") or "").strip()
    if not time_text:
        return None
    show_format, categories = _parse_bottomsheet(raw)
    return Show(
        time=time_text,
        time_code=str(extra.get("showTimeCode") or ""),
        session_id=str(extra.get("sessionId") or ""),
        status=_status_from(categories, str(raw.get("styleId") or "")),
        show_format=show_format,
        categories=categories,
    )


def _venue_url(card: dict) -> str:
    header = ((card.get("header") or {}).get("data") or {})
    for comp in header.get("components") or []:
        if not isinstance(comp, dict):
            continue
        cta = (comp.get("data") or {}).get("cta") or {}
        url = (cta.get("additionalData") or {}).get("redirectionUrl")
        if url:
            return str(url)
    return ""


def _parse_venue(card: dict) -> Venue | None:
    extra = card.get("additionalData") or {}
    name = str(extra.get("venueName") or "").strip()
    if not name:
        return None
    shows: list[Show] = []
    for section in card.get("showtimesSections") or []:
        if not isinstance(section, dict):
            continue
        for raw in section.get("showtimes") or []:
            if isinstance(raw, dict):
                show = _parse_show(raw)
                if show:
                    shows.append(show)
    shows.sort(key=lambda s: s.minutes)
    return Venue(
        name=name,
        code=str(extra.get("venueCode") or ""),
        info=[
            str(i.get("label"))
            for i in card.get("infoList") or []
            if isinstance(i, dict) and i.get("label")
        ],
        url=_venue_url(card),
        shows=shows,
    )


def parse_venues(payload: dict) -> list[Venue]:
    """Read every cinema and its showtimes out of the payload."""
    venues: list[Venue] = []
    for widget in payload.get("showtimeWidgets") or []:
        if not isinstance(widget, dict) or widget.get("type") != "groupList":
            continue
        for group in widget.get("data") or []:
            if not isinstance(group, dict) or group.get("type") != "venueGroup":
                continue
            for card in group.get("data") or []:
                if isinstance(card, dict) and card.get("type") == "venue-card":
                    venue = _parse_venue(card)
                    if venue:
                        venues.append(venue)
    return venues


def parse_day(payload: dict, date_code: str, dates: list[DateOption]) -> DayResult:
    label = next(
        (d.label for d in dates if d.date_code == date_code),
        DateOption(date_code, "", "", "", True, True).iso,
    )
    return DayResult(date_code=date_code, label=label, venues=parse_venues(payload))
