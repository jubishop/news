"""One durable incident per active problem; delivery runs outside requests."""

import secrets

from . import clock


def observe(
    connection, key, kind, message, *, reporter_id=None, run_id=None, worker_id=None
):
    existing = connection.execute(
        "SELECT id FROM incidents WHERE incident_key=? AND resolved_at IS NULL", (key,)
    ).fetchone()
    if existing:
        connection.execute(
            "UPDATE incidents SET last_seen_at=?,message=? WHERE id=?",
            (clock.now(), message, existing["id"]),
        )
        return existing["id"]
    identity = secrets.token_hex(16)
    connection.execute(
        """INSERT INTO incidents
        (id,incident_key,kind,message,reporter_id,run_id,worker_id,first_seen_at,last_seen_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            identity,
            key,
            kind,
            message,
            reporter_id,
            run_id,
            worker_id,
            clock.now(),
            clock.now(),
        ),
    )
    return identity


def resolve(connection, key):
    connection.execute(
        "UPDATE incidents SET resolved_at=? WHERE incident_key=? AND resolved_at IS NULL",
        (clock.now(), key),
    )
