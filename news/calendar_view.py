"""Read-only projections of active reporting schedules for one Pacific month."""

import calendar
from datetime import date
import json
import re

from . import clock, schedules
from .db import many
from .errors import Problem


def month_view(connection, value=None):
    today = clock.today()
    value = today.isoformat()[:7] if value is None else value
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", value):
            raise ValueError
        first = date.fromisoformat(value + "-01")
    except ValueError:
        raise Problem("Choose a calendar month as YYYY-MM.") from None

    roster = many(
        connection,
        """SELECT id,name,schedule_json,schedule_effective_date FROM reporters
        WHERE deleted_at IS NULL AND completed_at IS NULL AND paused=0
        ORDER BY name,id""",
    )
    for reporter in roster:
        reporter["schedule"] = json.loads(reporter.pop("schedule_json"))
    today_runs = {
        run["reporter_id"]: run["state"]
        for run in many(
            connection,
            "SELECT reporter_id,state FROM runs WHERE expected_date=?",
            (today.isoformat(),),
        )
    }
    days = []
    for number in range(1, calendar.monthrange(first.year, first.month)[1] + 1):
        day = first.replace(day=number)
        entries = []
        if day >= today:
            for reporter in roster:
                if day == today and reporter["id"] in today_runs:
                    # Saved work predates any schedule edit that starts tomorrow.
                    due = today_runs[reporter["id"]] in ("pending", "running", "retry_wait")
                else:
                    due = (
                        day.isoformat() >= reporter["schedule_effective_date"]
                        and schedules.occurs(reporter["schedule"], day)
                    )
                if due:
                    entries.append(reporter)
        days.append({"date": day, "entries": entries, "today": day == today, "past": day < today})

    previous = (
        first.replace(month=first.month - 1) if first.month > 1
        else date(first.year - 1, 12, 1) if first.year > 1 else None
    )
    following = (
        first.replace(month=first.month + 1) if first.month < 12
        else date(first.year + 1, 1, 1) if first.year < 9999 else None
    )
    return {
        "label": first.strftime("%B %Y"),
        "previous": previous.isoformat()[:7] if previous else None,
        "next": following.isoformat()[:7] if following else None,
        "current": today.isoformat()[:7],
        "padding": range(first.weekday()),
        "days": days,
        "empty": not any(day["entries"] for day in days),
    }
