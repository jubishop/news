"""Resend delivery with durable payloads and a bounded idempotency window."""

import json
import urllib.error
import urllib.request

from . import clock, validation as v
from .db import many, one, transaction


def deliver(config):
    if not config.get("RESEND_API_KEY") or not config.get("ALERT_TO"):
        return 0
    sent = 0
    with transaction(config["DATABASE"]) as connection:
        ids = [
            row["id"]
            for row in many(
                connection,
                """SELECT id FROM incidents
            WHERE resolved_at IS NULL AND notification_sent_at IS NULL
            AND (notification_retry_at IS NULL OR notification_retry_at<=?)
            AND (notification_started_at IS NULL OR notification_started_at>?)
            AND (kind NOT IN ('run_overdue','run_failed') OR NOT EXISTS
                (SELECT 1 FROM incidents outage WHERE outage.kind='worker_missing' AND outage.resolved_at IS NULL))
            ORDER BY first_seen_at LIMIT 20""",
                (clock.now(), clock.now() - 23 * 3600),
            )
        ]
    with transaction(config["DATABASE"], write=True) as connection:
        connection.execute(
            """UPDATE incidents SET notification_error='Delivery uncertain; reconcile with Resend before retrying'
            WHERE resolved_at IS NULL AND notification_sent_at IS NULL AND notification_started_at<=?""",
            (clock.now() - 23 * 3600,),
        )
    for identity in ids:
        with transaction(config["DATABASE"], write=True) as connection:
            incident = one(
                connection, "SELECT * FROM incidents WHERE id=?", (identity,)
            )
            if (
                incident["resolved_at"]
                or incident["notification_sent_at"]
                or (
                    incident["notification_retry_at"]
                    and incident["notification_retry_at"] > clock.now()
                )
            ):
                continue
            # One outage email covers missing or failed results during worker silence.
            if (
                incident["kind"] in ("run_overdue", "run_failed")
                and connection.execute(
                    "SELECT 1 FROM incidents WHERE kind='worker_missing' AND resolved_at IS NULL"
                ).fetchone()
            ):
                continue
            if (
                incident["notification_started_at"] is not None
                and clock.now() - incident["notification_started_at"] >= 23 * 3600
            ):
                connection.execute(
                    "UPDATE incidents SET notification_error='Delivery uncertain; reconcile with Resend before retrying' WHERE id=?",
                    (identity,),
                )
                continue
            payload = incident["notification_payload_json"] or v.canonical(
                {
                    "from": config["EMAIL_FROM"],
                    "to": [config["ALERT_TO"]],
                    "subject": "News · " + incident["kind"].replace("_", " "),
                    "text": incident["message"]
                    + "\n\nOpen your newsroom: "
                    + config["BASE_URL"].rstrip("/")
                    + "/newsroom",
                }
            )
            connection.execute(
                """UPDATE incidents SET notification_payload_json=?,
                notification_started_at=coalesce(notification_started_at,?),notification_attempts=notification_attempts+1,
                notification_retry_at=? WHERE id=?""",
                (payload, clock.now(), clock.now() + 300, identity),
            )
        request = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload.encode(),
            headers={
                "Authorization": "Bearer " + config["RESEND_API_KEY"],
                "Content-Type": "application/json",
                "Idempotency-Key": "news-incident/" + identity,
                "User-Agent": "News/1",
            },
            method="POST",
        )
        error_message, receipt, rejected = None, None, False
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                receipt = json.load(response)
            if (
                not isinstance(receipt, dict)
                or not isinstance(receipt.get("id"), str)
                or not receipt["id"]
            ):
                raise ValueError("Missing receipt")
        except urllib.error.HTTPError as error:
            error_message = f"Resend HTTP {error.code}"
            rejected = (
                error.code in (400, 401, 403, 404, 422, 429)
                and incident["notification_started_at"] is None
            )
            error.close()
        except (OSError, ValueError):
            error_message = "Email delivery failed; pending safe retry"
        with transaction(config["DATABASE"], write=True) as connection:
            if error_message:
                connection.execute(
                    """UPDATE incidents SET notification_error=?,notification_started_at=
                    CASE WHEN ? THEN NULL ELSE notification_started_at END WHERE id=?""",
                    (error_message, rejected, identity),
                )
            else:
                connection.execute(
                    """UPDATE incidents SET notification_sent_at=?,notification_receipt_id=?,
                    notification_error=NULL,notification_retry_at=NULL WHERE id=?""",
                    (clock.now(), receipt["id"], identity),
                )
                sent += 1
    return sent
