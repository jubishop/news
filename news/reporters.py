"""Owner commands, with reporter identity retained after retirement."""

from datetime import date, timedelta
import json
import secrets

from . import clock, contractors, incidents, schedules, validation as v
from .db import one, many
from .errors import Problem


def get(connection, identity):
    row = one(connection, "SELECT * FROM reporters WHERE id=?", (identity,))
    if not row:
        raise Problem("Reporter not found.", 404, "not_found")
    row["schedule"] = json.loads(row["schedule_json"])
    if row["schedule"]["cadence"] == "once":
        row["schedule"] = schedules.parse(row["schedule"])
        today = clock.today().isoformat()
        row["fixed_dates"] = [day for day in row["schedule"]["dates"] if day <= today]
        row["future_dates"] = [day for day in row["schedule"]["dates"] if day > today]
    row["cadence_label"] = schedules.label(row["schedule"])
    row["next_date"] = None
    if not row["deleted_at"] and not row["completed_at"]:
        pending = one(
            connection,
            """SELECT expected_date FROM runs WHERE reporter_id=?
            AND state IN ('pending','running','retry_wait') ORDER BY expected_date LIMIT 1""",
            (identity,),
        )
        if row["schedule"]["cadence"] == "once":
            remaining = contractors.remaining_dates(connection, row)
            row["next_date"] = remaining[0] if remaining else None
        elif pending:
            row["next_date"] = pending["expected_date"]
        else:
            start = max(
                clock.today(), date.fromisoformat(row["schedule_effective_date"])
            )
            if connection.execute(
                "SELECT 1 FROM runs WHERE reporter_id=? AND expected_date=?",
                (identity, start.isoformat()),
            ).fetchone():
                start += timedelta(days=1)
            next_day = schedules.next_date(row["schedule"], start)
            row["next_date"] = next_day.isoformat() if next_day else None
    return row


def materialize(connection):
    today = clock.today()
    for reporter in many(
        connection,
        "SELECT * FROM reporters WHERE deleted_at IS NULL AND completed_at IS NULL",
    ):
        start = max(
            date.fromisoformat(reporter["schedule_effective_date"]),
            date.fromisoformat(reporter["materialized_through"]) + timedelta(days=1),
        )
        schedule = json.loads(reporter["schedule_json"])
        day = start
        while day <= today:
            if schedules.occurs(schedule, day):
                connection.execute(
                    """INSERT OR IGNORE INTO runs
                    (id,reporter_id,expected_date,kind,state,created_at) VALUES (?,?,?,'scheduled','pending',?)""",
                    (
                        secrets.token_hex(16),
                        reporter["id"],
                        day.isoformat(),
                        clock.now(),
                    ),
                )
            day += timedelta(days=1)
        if start <= today:
            connection.execute(
                "UPDATE reporters SET materialized_through=? WHERE id=?",
                (today.isoformat(), reporter["id"]),
            )


def save(connection, values, identity=None):
    name = v.text(values.get("name"), "Name", 120)
    prompt = v.text(values.get("prompt"), "Instructions", 64_000)
    schedule = schedules.parse(values)
    current = get(connection, identity) if identity else None
    if current and (current["deleted_at"] or current["completed_at"]):
        raise Problem("This reporter is retired.", 409, "retired")
    schedules.validate_change(schedule, current["schedule"] if current else None)
    changed_schedule = not current or schedule != current["schedule"]
    tomorrow = clock.today() + timedelta(days=1)
    if not current:
        identity = secrets.token_hex(16)
        connection.execute(
            """INSERT INTO reporters
            (id,name,prompt,schedule_json,schedule_effective_date,materialized_through,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                identity,
                name,
                prompt,
                v.canonical(schedule),
                tomorrow.isoformat(),
                clock.today().isoformat(),
                clock.now(),
                clock.now(),
            ),
        )
    else:
        materialize(connection)
        changed = (
            changed_schedule or name != current["name"] or prompt != current["prompt"]
        )
        if changed:
            connection.execute(
                """UPDATE reporters SET name=?,prompt=?,schedule_json=?,
                schedule_effective_date=?,config_version=config_version+1,updated_at=? WHERE id=?""",
                (
                    name,
                    prompt,
                    v.canonical(schedule),
                    tomorrow.isoformat()
                    if changed_schedule
                    else current["schedule_effective_date"],
                    clock.now(),
                    identity,
                ),
            )
        if schedule["cadence"] == "once" and prompt != current["prompt"]:
            for run in many(
                connection,
                "SELECT id FROM runs WHERE reporter_id=? AND state='failed' AND expected_date=?",
                (identity, schedule["dates"][-1]),
            ):
                connection.execute(
                    "UPDATE runs SET state='pending',finished_at=NULL,retry_not_before=NULL,retry_generation=retry_generation+1 WHERE id=?",
                    (run["id"],),
                )
                incidents.resolve(connection, "failed:" + run["id"])
        if schedule["cadence"] == "once" and not contractors.remaining_dates(
            connection, {"id": identity, "schedule": schedule}
        ):
            connection.execute(
                "UPDATE reporters SET completed_at=?,updated_at=? WHERE id=?",
                (clock.now(), clock.now(), identity),
            )
    return identity


def change_state(connection, identity, action):
    reporter = get(connection, identity)
    if reporter["deleted_at"] or reporter["completed_at"]:
        raise Problem("This reporter is retired.", 409, "retired")
    materialize(connection)
    if action == "delete":
        connection.execute(
            "UPDATE reporters SET deleted_at=?,updated_at=?,config_version=config_version+1 WHERE id=?",
            (clock.now(), clock.now(), identity),
        )
        connection.execute(
            """UPDATE runs SET state='cancelled',finished_at=?,closed_reason='Reporter removed'
            WHERE reporter_id=? AND state IN ('pending','retry_wait','skipped_paused')""",
            (clock.now(), identity),
        )
        connection.execute(
            "UPDATE incidents SET resolved_at=? WHERE reporter_id=? AND resolved_at IS NULL",
            (clock.now(), identity),
        )
    elif action in ("pause", "resume"):
        paused = int(action == "pause")
        if paused != reporter["paused"]:
            connection.execute(
                "UPDATE reporters SET paused=?,updated_at=?,config_version=config_version+1 WHERE id=?",
                (paused, clock.now(), identity),
            )
        if action == "resume" and reporter["schedule"]["cadence"] == "once":
            connection.execute(
                "UPDATE runs SET state='pending',finished_at=NULL WHERE reporter_id=? AND state='skipped_paused'",
                (identity,),
            )
    else:
        raise Problem("Unknown reporter action.", 404, "not_found")
