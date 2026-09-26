"""Calendar cadence, including clamped month ends. No coverage inference."""

import calendar
from datetime import timedelta

from . import validation as v
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
        result["date"] = v.calendar_date(
            values.get("date"), "Assignment date"
        ).isoformat()
    elif cadence != "daily":
        raise Problem("Choose daily, weekly, monthly, or one-time cadence.")
    return result


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
    return day.isoformat() == schedule["date"]


def next_date(schedule, start):
    if schedule["cadence"] == "once":
        day = v.calendar_date(schedule["date"], "Assignment date")
        return day if day >= start else None
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
    return "One-time · " + schedule["date"]
