"""Calendar cadence, including clamped month ends. No coverage inference."""

import calendar
from datetime import timedelta
import re

from . import clock, validation as v
from .errors import Problem

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def parse(values):
    cadence = values.get("cadence")
    result = {"cadence": cadence}
    if cadence == "weekly":
        days = (
            values.getlist("weekdays")
            if hasattr(values, "getlist")
            else values.get("weekdays", [])
        )
        if isinstance(days, str):
            days = [days]
        if (
            not isinstance(days, list)
            or not days
            or any(day not in WEEKDAYS for day in days)
        ):
            raise Problem("Choose at least one weekday.")
        result["weekdays"] = sorted(set(days), key=WEEKDAYS.index)
    elif cadence == "monthly":
        result["day_of_month"] = v.integer(
            values.get("day_of_month"), "Day of month", 1, 31
        )
    elif cadence == "once":
        raw = (
            values.getlist("dates")
            if hasattr(values, "getlist")
            else values.get("dates", [])
        )
        if "dates" not in values:
            raw = [values.get("date", "")]
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list) or any(
            not isinstance(value, str) for value in raw
        ):
            raise Problem("Enter assignment dates as YYYY-MM-DD, one per line.")
        dates = [
            v.calendar_date(value.strip(), "Assignment date").isoformat()
            for text in raw
            for value in re.split(r"[,\s]+", text.strip())
            if value
        ]
        if not dates:
            raise Problem("Choose at least one assignment date.")
        if len(set(dates)) != len(dates):
            raise Problem("Assignment dates must be distinct.")
        result["dates"] = sorted(dates)
    elif cadence != "daily":
        raise Problem("Choose daily, weekly, monthly, or contractor dates.")
    return result


def assignment_dates(schedule):
    """Read legacy single-date schedules without changing saved snapshots."""
    return schedule["dates"] if "dates" in schedule else [schedule["date"]]


def validate_change(schedule, previous=None):
    if previous and (
        (schedule["cadence"] == "once") != (previous["cadence"] == "once")
    ):
        raise Problem(
            "Create a new reporter to change between recurring and contractor work."
        )
    if schedule["cadence"] != "once":
        return
    today = clock.today().isoformat()
    old_dates = set(assignment_dates(previous)) if previous else set()
    dates = set(assignment_dates(schedule))
    if any(day <= today for day in old_dates - dates):
        raise Problem(
            "Dates already due stay fixed; you can still change future dates and instructions.",
            409,
            "assignment_due",
        )
    if any(day <= today for day in dates - old_dates):
        raise Problem("New assignment dates must be tomorrow or later.")


def occurs(schedule, day):
    cadence = schedule["cadence"]
    if cadence == "daily":
        return True
    if cadence == "weekly":
        return WEEKDAYS[day.weekday()] in schedule["weekdays"]
    if cadence == "monthly":
        return day.day == min(
            schedule["day_of_month"], calendar.monthrange(day.year, day.month)[1]
        )
    return day.isoformat() in assignment_dates(schedule)


def next_date(schedule, start):
    if schedule["cadence"] == "once":
        return next(
            (
                v.calendar_date(day, "Assignment date")
                for day in assignment_dates(schedule)
                if day >= start.isoformat()
            ),
            None,
        )
    for offset in range(370):
        day = start + timedelta(days=offset)
        if occurs(schedule, day):
            return day
    return None


def label(schedule):
    if schedule["cadence"] == "daily":
        return "Daily"
    if schedule["cadence"] == "weekly":
        return "Weekly · " + ", ".join(day.title() for day in schedule["weekdays"])
    if schedule["cadence"] == "monthly":
        return f"Monthly · day {schedule['day_of_month']}"
    dates = assignment_dates(schedule)
    return "Contractor · " + (dates[0] if len(dates) == 1 else f"{len(dates)} dates")
