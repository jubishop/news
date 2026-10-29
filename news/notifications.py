"""Resend delivery with durable payloads and a bounded idempotency window."""

import json
import urllib.error
import urllib.request

from . import clock, validation as v
from .db import many, one, transaction

# Resend keeps idempotency keys for 24 hours; stop retrying an unconfirmed send before then.
SAFE_WINDOW = 23 * 3600
UNCERTAIN = "Delivery uncertain; reconcile with Resend before retrying"


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
                (clock.now(), clock.now() - SAFE_WINDOW),
            )
        ]
    with transaction(config["DATABASE"], write=True) as connection:
        connection.execute(
            """UPDATE incidents SET notification_error=?
            WHERE resolved_at IS NULL AND notification_sent_at IS NULL AND notification_started_at<=?""",
            (UNCERTAIN, clock.now() - SAFE_WINDOW),
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
                and clock.now() - incident["notification_started_at"] >= SAFE_WINDOW
            ):
                connection.execute(
                    "UPDATE incidents SET notification_error=? WHERE id=?",
                    (UNCERTAIN, identity),
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
        receipt, error_message, refused = post(
            config, payload, "news-incident/" + identity
        )
        # A first attempt that Resend refused sent nothing, so its window restarts.
        rejected = refused and incident["notification_started_at"] is None
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
                    (clock.now(), receipt, identity),
                )
                sent += 1
    return sent


def post(config, payload, key):
    """Send one saved payload outside any transaction.

    Returns the receipt ID, an error message, and whether Resend refused the
    request outright, which means it did not accept the email.
    """
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload.encode(),
        headers={
            "Authorization": "Bearer " + config["RESEND_API_KEY"],
            "Content-Type": "application/json",
            "Idempotency-Key": key,
            "User-Agent": "News/1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            receipt = json.load(response)
        if (
            not isinstance(receipt, dict)
            or not isinstance(receipt.get("id"), str)
            or not receipt["id"]
        ):
            raise ValueError("Missing receipt")
        return receipt["id"], None, False
    except urllib.error.HTTPError as error:
        error.close()
        return None, f"Resend HTTP {error.code}", error.code in (400, 401, 403, 404, 422, 429)
    except (OSError, ValueError):
        return None, "Email delivery failed; pending safe retry", False
