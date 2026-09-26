"""UTC event times and Pacific reporting dates."""

from datetime import datetime
import time
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def now():
    return time.time()


def today():
    return datetime.fromtimestamp(now(), PACIFIC).date()


def display_time(value):
    if value is None:
        return "—"
    return datetime.fromtimestamp(value, PACIFIC).strftime("%b %-d, %Y · %-I:%M %p %Z")
