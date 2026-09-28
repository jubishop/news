"""Contractor completion and catch-up, retaining original runs and attempts."""

from . import clock, incidents, schedules
from .db import many, one


def satisfied_through(connection, reporter_id):
    row = one(
        connection,
        """SELECT max(expected_date) AS day FROM runs WHERE reporter_id=?
        AND state IN ('published','nothing_to_publish')""",
        (reporter_id,),
    )
    return row["day"] or ""


def remaining_dates(connection, reporter):
    through = satisfied_through(connection, reporter["id"])
    return [
        day for day in schedules.assignment_dates(reporter["schedule"])
        if day > through
    ]


def assignment_dates(connection, reporter, run):
    return [
        day for day in remaining_dates(connection, reporter)
        if day <= run["expected_date"]
    ]


def combine(connection, reporter, candidates):
    if not candidates:
        return []
    target = candidates[-1]
    dates = assignment_dates(connection, reporter, target)
    if len(dates) > 1:
        connection.execute(
            "UPDATE runs SET kind='catch_up' WHERE id=?", (target["id"],)
        )
        target["kind"] = "catch_up"
    for old in many(
        connection,
        """SELECT id FROM runs WHERE reporter_id=? AND expected_date<?
        AND state IN ('pending','retry_wait','skipped_paused')""",
        (reporter["id"], target["expected_date"]),
    ):
        connection.execute(
            """UPDATE runs SET state='superseded',superseded_by_run_id=?,finished_at=?,
            closed_reason='Combined into a later assignment' WHERE id=?""",
            (target["id"], clock.now(), old["id"]),
        )
        incidents.resolve(connection, "overdue:" + old["id"])
    return [target]


def annotate_history(connection, reporter, runs):
    if reporter["schedule"]["cadence"] != "once":
        return
    successes = many(
        connection,
        """SELECT id,expected_date FROM runs WHERE reporter_id=?
        AND state IN ('published','nothing_to_publish') ORDER BY expected_date""",
        (reporter["id"],),
    )
    for run in runs:
        run["satisfied_by_run_id"] = next(
            (
                success["id"] for success in successes
                if success["expected_date"] >= run["expected_date"]
            ),
            None,
        )
