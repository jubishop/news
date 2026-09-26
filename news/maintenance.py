"""Periodic server bookkeeping; never invokes AI or research services."""

from datetime import timedelta

from . import clock, content, incidents, reporters
from .db import one, many, transaction


def maintain(config):
    with transaction(config["DATABASE"], write=True) as connection:
        reporters.materialize(connection)
        purged = content.purge(connection)
        worker = config["WORKER_ID"]
        yesterday = (clock.today() - timedelta(days=1)).isoformat()
        latest = one(
            connection,
            "SELECT * FROM worker_checkins WHERE worker_id=? ORDER BY received_at DESC LIMIT 1",
            (worker,),
        )
        monitoring = config["MONITOR_WORKER"]
        start = config.get("MONITOR_START_DATE") or clock.today().isoformat()
        outage = (
            monitoring
            and start <= yesterday
            and (not latest or latest["reporting_date"] < yesterday)
        )
        if outage:
            incidents.observe(
                connection,
                "worker:" + worker,
                "worker_missing",
                "The reporting worker missed a complete Pacific calendar day. Some assignments may be late.",
                worker_id=worker,
            )
        elif latest and latest["reporting_date"] >= yesterday:
            incidents.resolve(connection, "worker:" + worker)
        for run in many(
            connection,
            """SELECT r.* FROM runs r JOIN reporters p ON p.id=r.reporter_id
            WHERE r.expected_date<? AND r.state IN ('pending','running','retry_wait') AND p.deleted_at IS NULL""",
            (clock.today().isoformat(),),
        ):
            incidents.observe(
                connection,
                "overdue:" + run["id"],
                "run_overdue",
                "An assignment has not returned a result by the end of its reporting day.",
                reporter_id=run["reporter_id"],
                run_id=run["id"],
                worker_id=worker,
            )
    return {"purged_articles": purged, "worker_outage": bool(outage)}
