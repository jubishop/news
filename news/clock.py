"""UTC event times and Pacific reporting dates."""

from datetime import date, datetime
import time
from zoneinfo import ZoneInfo

from markupsafe import Markup, escape

PACIFIC = ZoneInfo("America/Los_Angeles")


def now():
    return time.time()


def today():
    return datetime.fromtimestamp(now(), PACIFIC).date()


def display_time(value):
    if value is None:
        return "—"
    return datetime.fromtimestamp(value, PACIFIC).strftime("%b %-d, %Y · %-I:%M %p %Z")


# Calendar dates are displayed as parts: (date, text) pieces and separator
# strings, so text and <time> markup share one set of formatting rules. Values
# are datetime.date objects or stored YYYY-MM-DD strings. The year appears only
# outside the current Pacific year.


def _day(value):
    return value if isinstance(value, date) else date.fromisoformat(value)


def _year(day):
    return "" if day.year == today().year else f", {day.year}"


def _single(value, pattern):
    if value is None:
        return ["—"]
    day = _day(value)
    return [(day, day.strftime(pattern) + f" {day.day}{_year(day)}")]


def _range(start, end):
    start, end = _day(start), _day(end)
    if start == end:
        return _single(start, "%a, %b")
    if start.year != end.year:
        return [(start, f"{start:%b} {start.day}, {start.year}"), " – ",
                (end, f"{end:%b} {end.day}, {end.year}")]
    first = (start, f"{start:%b} {start.day}")
    if start.month == end.month:
        return [first, "–", (end, f"{end.day}{_year(end)}")]
    return [first, " – ", (end, f"{end:%b} {end.day}{_year(end)}")]


def _text(parts):
    return "".join(part if isinstance(part, str) else part[1] for part in parts)


def _markup(parts):
    return Markup("").join(
        escape(part) if isinstance(part, str)
        else Markup('<time datetime="{}">{}</time>').format(part[0].isoformat(), part[1])
        for part in parts
    )


def short_date(value):
    """`Sun, Oct 11`, or `Sat, Oct 11, 2025` outside the current Pacific year."""
    return _text(_single(value, "%a, %b"))


def long_date(value):
    """`Sunday, Oct 11`, or `Saturday, Oct 11, 2025` in another year."""
    return _text(_single(value, "%A, %b"))


def date_range(start, end):
    """Inclusive range, such as `Oct 5–11` or `Sep 28 – Oct 4`; one day is a short date."""
    return _text(_range(start, end))


def short_date_html(value):
    return _markup(_single(value, "%a, %b"))


def long_date_html(value):
    return _markup(_single(value, "%A, %b"))


def date_range_html(start, end):
    return _markup(_range(start, end))
