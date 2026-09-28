"""Worker protocol. Call these operations inside one SQLite write transaction."""

import hashlib
import hmac
import json
import secrets

from . import clock, contractors, incidents, reporters, validation as v
from .db import one, many
from .errors import Problem

LEASE_SECONDS = 6 * 3600
RETRY_DELAY = 15 * 60
MAX_ATTEMPTS = 3


def get_run(connection, identity):
    run = one(connection, "SELECT * FROM runs WHERE id=?", (identity,))
    if not run:
        raise Problem("Assignment not found.", 404, "not_found")
    return run


def late(run):
    return run["expected_date"] < clock.today().isoformat() and run["state"] in (
        "pending",
        "running",
        "retry_wait",
    )


def removed_problem(run, worker):
    return Problem(
        "New work for a removed reporter is not allowed.",
        409,
        "reporter_removed",
        {
            "key": "removed:" + run["reporter_id"],
            "kind": "invalid_reporting",
            "message": "The worker attempted new work for a removed reporter.",
            "reporter_id": run["reporter_id"],
            "run_id": run["id"],
            "worker_id": worker,
        },
    )


def discover(connection, worker, values):
    v.object_fields(values, ("request_id",), ("request_id",))
    request_id = v.identifier(values["request_id"])
    reporters.materialize(connection)
    connection.execute(
        """INSERT OR IGNORE INTO worker_checkins
        (id,worker_id,request_id,received_at,reporting_date) VALUES (?,?,?,?,?)""",
        (
            secrets.token_hex(16),
            worker,
            request_id,
            clock.now(),
            clock.today().isoformat(),
        ),
    )
    checkin = one(
        connection,
        "SELECT reporting_date FROM worker_checkins WHERE worker_id=? AND request_id=?",
        (worker, request_id),
    )
    if checkin["reporting_date"] == clock.today().isoformat():
        incidents.resolve(connection, "worker:" + worker)
    output = []
    for row in many(
        connection,
        "SELECT id FROM reporters WHERE deleted_at IS NULL AND completed_at IS NULL ORDER BY created_at,id",
    ):
        reporter = reporters.get(connection, row["id"])
        active = one(
            connection,
            """SELECT r.* FROM runs r JOIN run_attempts a ON a.run_id=r.id
            WHERE r.reporter_id=? AND a.outcome IS NULL""",
            (row["id"],),
        )
        if active:
            candidates = [active]
        else:
            candidates = many(
                connection,
                """SELECT * FROM runs WHERE reporter_id=?
                AND state IN ('pending','retry_wait') ORDER BY expected_date,id""",
                (row["id"],),
            )
            if reporter["schedule"]["cadence"] == "once":
                candidates = contractors.combine(connection, reporter, candidates)
            else:
                missed = [
                    run
                    for run in candidates
                    if run["expected_date"] < clock.today().isoformat()
                ]
                if missed:
                    target = one(
                        connection,
                        "SELECT * FROM runs WHERE reporter_id=? AND expected_date=?",
                        (row["id"], clock.today().isoformat()),
                    )
                    if not target:
                        identity = secrets.token_hex(16)
                        connection.execute(
                            """INSERT INTO runs (id,reporter_id,expected_date,kind,state,created_at)
                            VALUES (?,?,?,'catch_up','pending',?)""",
                            (
                                identity,
                                row["id"],
                                clock.today().isoformat(),
                                clock.now(),
                            ),
                        )
                        target = get_run(connection, identity)
                    elif target["state"] == "pending":
                        connection.execute(
                            "UPDATE runs SET kind='catch_up' WHERE id=?",
                            (target["id"],),
                        )
                        target["kind"] = "catch_up"
                    for old in missed:
                        connection.execute(
                            """UPDATE runs SET state='superseded',superseded_by_run_id=?,finished_at=?,
                            closed_reason='Combined into a current assignment' WHERE id=?""",
                            (target["id"], clock.now(), old["id"]),
                        )
                        incidents.resolve(connection, "overdue:" + old["id"])
                    candidates = (
                        [target] if target["state"] in ("pending", "retry_wait") else []
                    )
        if not candidates:
            continue
        run = candidates[0]
        if run["retry_not_before"] and run["retry_not_before"] > clock.now():
            continue
        attempt = one(
            connection,
            "SELECT id,claim_expires_at FROM run_attempts WHERE run_id=? AND outcome IS NULL",
            (run["id"],),
        )
        run.update(reporter=reporter, late=late(run), current_attempt=attempt)
        if reporter["schedule"]["cadence"] == "once":
            run["assignment_dates"] = contractors.assignment_dates(connection, reporter, run)
        output.append(run)
    return {"reporting_date": clock.today().isoformat(), "runs": output}


def token_hash(token):
    token = v.text(token, "ownership_token", 256)
    if len(token) < 32:
        raise Problem("ownership_token must contain at least 32 random characters.")
    return hashlib.sha256(token.encode()).hexdigest()


def claim_receipt(attempt, token):
    return {
        "attempt_id": attempt["id"],
        "attempt_number": attempt["attempt_number"],
        "ownership_token": token,
        "claim_expires_at": attempt["claim_expires_at"],
        "acknowledgment_only": bool(attempt["acknowledgment_only"]),
        "reporter": json.loads(attempt["config_snapshot_json"]),
    }


def claim(connection, run_id, worker, values):
    v.object_fields(
        values,
        ("request_id", "ownership_token", "replace_attempt_id"),
        ("request_id", "ownership_token"),
    )
    request_id = v.identifier(values["request_id"])
    hashed = token_hash(values["ownership_token"])
    run = get_run(connection, run_id)
    existing = one(
        connection,
        "SELECT * FROM run_attempts WHERE worker_id=? AND request_id=?",
        (worker, request_id),
    )
    if existing:
        if existing["run_id"] != run_id or not hmac.compare_digest(
            existing["claim_token_hash"], hashed
        ):
            raise Problem(
                "Claim request ID is already used with different data.",
                409,
                "claim_conflict",
            )
        return claim_receipt(existing, values["ownership_token"])
    reporter = reporters.get(connection, run["reporter_id"])
    if reporter["deleted_at"]:
        raise removed_problem(run, worker)
    if reporter["completed_at"] or run["state"] not in (
        "pending",
        "retry_wait",
        "running",
    ):
        raise Problem("This assignment is not available.", 409, "run_closed")
    if run["retry_not_before"] and run["retry_not_before"] > clock.now():
        raise Problem("The retry delay has not elapsed.", 409, "retry_later")
    active = one(
        connection,
        """SELECT a.* FROM run_attempts a JOIN runs r ON r.id=a.run_id
        WHERE r.reporter_id=? AND a.outcome IS NULL""",
        (reporter["id"],),
    )
    if active:
        if (
            active["run_id"] != run_id
            or active["id"] != values.get("replace_attempt_id")
            or active["worker_id"] != worker
        ):
            raise Problem(
                "A reporting attempt is already active.", 409, "attempt_active"
            )
        connection.execute(
            """UPDATE run_attempts SET outcome='failed',finished_at=?,error_code='abandoned',
            error_message='Worker replaced unfinished work',retryable=1 WHERE id=?""",
            (clock.now(), active["id"]),
        )
    count = connection.execute(
        """SELECT count(*) FROM run_attempts WHERE run_id=? AND retry_generation=?
        AND acknowledgment_only=0""",
        (run_id, run["retry_generation"]),
    ).fetchone()[0]
    if not reporter["paused"] and count >= MAX_ATTEMPTS:
        connection.execute(
            "UPDATE runs SET state='failed',finished_at=?,retry_not_before=NULL WHERE id=?",
            (clock.now(), run_id),
        )
        incidents.resolve(connection, "overdue:" + run_id)
        incidents.observe(
            connection,
            "failed:" + run_id,
            "run_failed",
            "The worker exhausted its attempts after abandoning unfinished work.",
            reporter_id=reporter["id"],
            run_id=run_id,
            worker_id=worker,
        )
        raise Problem(
            "The research attempt allowance is exhausted.",
            409,
            "retry_exhausted",
            commit=True,
        )
    identity = secrets.token_hex(16)
    number = connection.execute(
        "SELECT coalesce(max(attempt_number),0)+1 FROM run_attempts WHERE run_id=?",
        (run_id,),
    ).fetchone()[0]
    if reporter["schedule"]["cadence"] == "once":
        contractors.combine(connection, reporter, [run])
    snapshot = {
        key: reporter[key]
        for key in ("id", "name", "prompt", "schedule", "paused", "config_version")
    }
    if reporter["schedule"]["cadence"] == "once":
        snapshot["assignment_dates"] = contractors.assignment_dates(connection, reporter, run)
    connection.execute(
        """INSERT INTO run_attempts
        (id,run_id,attempt_number,retry_generation,worker_id,request_id,acknowledgment_only,
        config_snapshot_json,started_at,claim_token_hash,claim_expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            identity,
            run_id,
            number,
            run["retry_generation"],
            worker,
            request_id,
            int(reporter["paused"]),
            v.canonical(snapshot),
            clock.now(),
            hashed,
            clock.now() + LEASE_SECONDS,
        ),
    )
    connection.execute(
        "UPDATE runs SET state='running',retry_not_before=NULL WHERE id=?", (run_id,)
    )
    attempt = one(connection, "SELECT * FROM run_attempts WHERE id=?", (identity,))
    return claim_receipt(attempt, values["ownership_token"])


def authorized_attempt(connection, run_id, worker, values):
    attempt = one(
        connection,
        "SELECT * FROM run_attempts WHERE id=? AND run_id=?",
        (v.identifier(values.get("attempt_id"), "attempt_id"), run_id),
    )
    hashed = token_hash(values.get("ownership_token"))
    if (
        not attempt
        or attempt["worker_id"] != worker
        or not hmac.compare_digest(attempt["claim_token_hash"], hashed)
    ):
        raise Problem("Invalid attempt ownership.", 403, "invalid_ownership")
    return attempt


def renew(connection, run_id, worker, values):
    v.object_fields(
        values, ("attempt_id", "ownership_token"), ("attempt_id", "ownership_token")
    )
    attempt = authorized_attempt(connection, run_id, worker, values)
    if attempt["outcome"]:
        raise Problem("This attempt has finished.", 409, "attempt_closed")
    expires = clock.now() + LEASE_SECONDS
    connection.execute(
        "UPDATE run_attempts SET claim_expires_at=? WHERE id=?",
        (expires, attempt["id"]),
    )
    return {"attempt_id": attempt["id"], "claim_expires_at": expires}


def result(connection, run_id, worker, values):
    allowed = (
        "submission_id",
        "attempt_id",
        "ownership_token",
        "outcome",
        "articles",
        "reason",
        "error",
    )
    v.object_fields(
        values,
        allowed,
        ("submission_id", "attempt_id", "ownership_token", "outcome", "articles"),
    )
    submission = v.identifier(values["submission_id"], "submission_id")
    run = get_run(connection, run_id)
    attempt = authorized_attempt(connection, run_id, worker, values)
    digest = hashlib.sha256(v.canonical(values).encode()).hexdigest()
    reporter = reporters.get(connection, run["reporter_id"])
    received = one(
        connection,
        "SELECT * FROM run_attempts WHERE worker_id=? AND submission_id=?",
        (worker, submission),
    )
    if received:
        if received["id"] == attempt["id"] and hmac.compare_digest(
            received["payload_hash"], digest
        ):
            return json.loads(received["receipt_json"])
        if reporter["deleted_at"]:
            raise removed_problem(run, worker)
        raise Problem(
            "Submission ID was already used with different data.",
            409,
            "submission_conflict",
        )
    if attempt["outcome"] or run["state"] != "running":
        if reporter["deleted_at"]:
            raise removed_problem(run, worker)
        raise Problem("This attempt is no longer current.", 409, "attempt_closed")
    outcome = values["outcome"]
    if outcome not in ("published", "nothing_to_publish", "skipped_paused", "failed"):
        raise Problem("Unknown reporting outcome.")
    if attempt["acknowledgment_only"] and outcome != "skipped_paused":
        raise Problem(
            "This claim is only for acknowledging a pause.", 409, "paused_claim"
        )
    if outcome == "skipped_paused" and not (
        reporter["paused"] or attempt["acknowledgment_only"]
    ):
        raise Problem("The reporter is not paused.", 409, "not_paused")
    articles = values["articles"]
    if (
        not isinstance(articles, list)
        or len(articles) > 20
        or (outcome == "published") != bool(articles)
    ):
        raise Problem(
            "Published results need 1–20 articles; other outcomes need an empty list."
        )
    articles = [v.article(article) for article in articles]
    reason = (
        v.text(values.get("reason"), "Reason", 4000)
        if outcome in ("nothing_to_publish", "skipped_paused")
        else None
    )
    error = None
    if outcome == "failed":
        error = values.get("error")
        v.object_fields(
            error, ("code", "message", "retryable"), ("code", "message", "retryable")
        )
        error = {
            "code": v.identifier(error["code"], "error code"),
            "message": v.text(error["message"], "Error message", 4000),
            "retryable": error["retryable"],
        }
        if type(error["retryable"]) is not bool:
            raise Problem("retryable must be a boolean.")
    ids = []
    for article in articles:
        identity = secrets.token_hex(16)
        ids.append(identity)
        connection.execute(
            """INSERT INTO articles (id,reporter_id,attempt_id,reporter_name,title,summary,
            body_markdown,sources_json,article_date,coverage_start,coverage_end,published_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                identity,
                reporter["id"],
                attempt["id"],
                json.loads(attempt["config_snapshot_json"])["name"],
                article["title"],
                article["summary"],
                article["body_markdown"],
                v.canonical(article["sources"]),
                article["article_date"],
                article["coverage_start"],
                article["coverage_end"],
                clock.now(),
            ),
        )
    receipt = {
        "run_id": run_id,
        "submission_id": submission,
        "outcome": outcome,
        "article_ids": ids,
    }
    connection.execute(
        """UPDATE run_attempts SET outcome=?,finished_at=?,reason=?,error_code=?,
        error_message=?,retryable=?,submission_id=?,payload_hash=?,receipt_json=? WHERE id=?""",
        (
            outcome,
            clock.now(),
            reason,
            error["code"] if error else None,
            error["message"] if error else None,
            int(error["retryable"]) if error else None,
            submission,
            digest,
            v.canonical(receipt),
            attempt["id"],
        ),
    )
    state, retry_at, finished = outcome, None, clock.now()
    if outcome == "failed":
        count = connection.execute(
            "SELECT count(*) FROM run_attempts WHERE run_id=? AND retry_generation=? AND acknowledgment_only=0",
            (run_id, run["retry_generation"]),
        ).fetchone()[0]
        if error["retryable"] and count < MAX_ATTEMPTS and not reporter["deleted_at"]:
            state, retry_at, finished = "retry_wait", clock.now() + RETRY_DELAY, None
        else:
            incidents.observe(
                connection,
                "failed:" + run_id,
                "run_failed",
                "A reporting assignment exhausted its retries or reported a final failure.",
                reporter_id=reporter["id"],
                run_id=run_id,
                worker_id=worker,
            )
    if outcome == "skipped_paused" and reporter["schedule"]["cadence"] == "once":
        finished = None
        if not reporter["paused"] and not reporter["deleted_at"]:
            state = "pending"
    connection.execute(
        "UPDATE runs SET state=?,retry_not_before=?,finished_at=? WHERE id=?",
        (state, retry_at, finished, run_id),
    )
    if outcome in ("published", "nothing_to_publish"):
        incidents.resolve(connection, "overdue:" + run_id)
        connection.execute(
            """UPDATE incidents SET resolved_at=? WHERE reporter_id=? AND kind='run_failed'
            AND resolved_at IS NULL AND run_id IN
                (SELECT id FROM runs WHERE reporter_id=? AND expected_date<=?)""",
            (clock.now(), reporter["id"], reporter["id"], run["expected_date"]),
        )
        if reporter["schedule"]["cadence"] == "once" and not contractors.remaining_dates(
            connection, reporter
        ):
            connection.execute(
                "UPDATE reporters SET completed_at=?,updated_at=? WHERE id=?",
                (clock.now(), clock.now(), reporter["id"]),
            )
    if outcome == "skipped_paused" or state == "failed":
        incidents.resolve(connection, "overdue:" + run_id)
    return receipt
