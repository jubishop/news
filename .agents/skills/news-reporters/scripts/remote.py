"""Executed by the SSH helper in the deployed virtual environment, as news."""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


def read_database(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def view(reporters, connection, identity):
    row = reporters.get(connection, identity)
    fields = ("id", "name", "prompt", "schedule", "config_version", "paused",
              "deleted_at", "completed_at", "schedule_effective_date", "next_date")
    return {key: row[key] for key in fields}


def backup_database(database, directory):
    directory = Path(directory)
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.stat().st_mode & 0o077:
        raise OSError("Backup directory must be private (mode 0700).")
    descriptor, temporary = tempfile.mkstemp(prefix=".reporters-", suffix=".sqlite3", dir=directory)
    os.close(descriptor)
    temporary = Path(temporary)
    destination = directory / "reporters-before-change.sqlite3"
    try:
        with closing(read_database(database)) as source, closing(sqlite3.connect(temporary)) as backup:
            source.backup(backup)
            if backup.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise OSError("Reporter backup failed its integrity check.")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return str(destination)


def prepare_values(request, before):
    from news import schedules, validation
    from news.errors import Problem

    patch = request["values"]
    values = {"name": before["name"], "prompt": before["prompt"], **before["schedule"]} if before else {}
    values.update(patch)
    schedule_fields = {"daily": set(), "weekly": {"weekdays"},
                       "monthly": {"day_of_month"}, "once": {"dates"}}
    if set(patch) - ({"name", "prompt", "cadence"} | schedule_fields.get(values.get("cadence"), set())):
        raise Problem("Unsupported fields for this schedule. Send only the fields being changed.")
    values["name"] = validation.text(values.get("name"), "Name", 120)
    values["prompt"] = validation.text(values.get("prompt"), "Instructions", 64_000)
    schedule = schedules.parse(values)
    schedules.validate_change(schedule, before["schedule"] if before else None)
    return {"name": values["name"], "prompt": values["prompt"], **schedule}


def mutate(request, state):
    from news import reporters
    from news.db import transaction
    from news.errors import Problem

    action = request["action"]
    if action not in ("create", "update", "pause", "resume", "delete"):
        raise Problem("Unknown reporter operation.")
    identity = request.get("id")
    with transaction(request["database"], write=True) as connection:
        before = view(reporters, connection, identity) if identity else None
        if action != "create":
            if before is None:
                raise Problem("Reporter ID is required.")
            if before["config_version"] != request.get("if_version"):
                raise Problem("Reporter changed since it was read. Read it again before editing.",
                              409, "stale_version")
            if before["deleted_at"] is not None or before["completed_at"] is not None:
                raise Problem("This reporter is retired.", 409, "retired")
        values = prepare_values(request, before) if action in ("create", "update") else None
        if values:
            for row in connection.execute("SELECT id,name FROM reporters WHERE deleted_at IS NULL AND completed_at IS NULL"):
                if row["id"] != identity and row["name"].casefold() == values["name"].casefold():
                    raise Problem("An active reporter already has that name. Inspect it before creating or renaming.",
                                  409, "duplicate_name")
        state["backup_path"] = backup_database(request["database"], request["backup_dir"])
        if values:
            identity = reporters.save(connection, values, identity)
        else:
            reporters.change_state(connection, identity, action)
        state["id"] = identity
        saved = view(reporters, connection, identity)
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise Problem("Database foreign-key check failed; change rolled back.")
    state["committed"] = True
    with closing(read_database(request["database"])) as connection:
        after = view(reporters, connection, identity)
    # Worker activity may change the next due date after the transaction commits.
    if any(after[key] != saved[key] for key in saved if key != "next_date"):
        raise Problem("Saved reporter changed before verification. Read it again before another edit.",
                      409, "verification_changed")
    return {"action": action, "before": before, "after": after,
            "backup_path": state["backup_path"], "verified": True}


def main():
    request = json.load(sys.stdin)
    sys.path.insert(0, str(Path(request["release"]).resolve()))
    from news import reporters
    from news.errors import Problem

    state = {"committed": False}
    try:
        with closing(read_database(request["database"])) as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] not in (2, 3):
                raise Problem("Unsupported database schema; inspect the deployed release.")
            if request["action"] == "list":
                condition = "" if request.get("all") else " WHERE deleted_at IS NULL AND completed_at IS NULL"
                rows = connection.execute("SELECT id FROM reporters" + condition + " ORDER BY name,id").fetchall()
                roster = [view(reporters, connection, row["id"]) for row in rows]
                for row in roster:
                    del row["prompt"]
                print(json.dumps({"reporters": roster}))
                return 0
            if request["action"] == "show":
                print(json.dumps({"reporter": view(reporters, connection, request["id"])}))
                return 0
        print(json.dumps(mutate(request, state)))
        return 0
    except Problem as error:
        print(json.dumps({"error": error.code, "message": str(error), **state}))
        return 1
    except (OSError, sqlite3.Error) as error:
        print(json.dumps({"error": "operation_failed", "message": str(error), **state}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
