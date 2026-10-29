"""The owner's daily newsletter: assembled by maintenance, delivered like alerts."""

from jinja2 import Environment, PackageLoader, select_autoescape

from . import clock, content, notifications, validation as v
from .db import many, transaction

RETENTION_SECONDS = 30 * 24 * 3600
RETRY_SECONDS = 300
templates = Environment(
    loader=PackageLoader("news"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def configured(config):
    return bool(config.get("RESEND_API_KEY") and config.get("ALERT_TO"))


def prepare(connection, config):
    """Save today's newsletter once the day's reporting has finished.

    Call inside maintenance's write transaction, after runs are materialized.
    Returns the number of articles covered, or None when nothing was decided.
    A day with no new articles is recorded without an email, so later articles
    wait for the next morning.
    """
    connection.execute(
        "DELETE FROM newsletters WHERE created_at<=?",
        (clock.now() - RETENTION_SECONDS,),
    )
    today = clock.today().isoformat()
    if not configured(config) or connection.execute(
        "SELECT 1 FROM newsletters WHERE newsletter_date=?", (today,)
    ).fetchone():
        return None
    # Until the worker checks in, today's work may not have started at all.
    checked_in = connection.execute(
        "SELECT 1 FROM worker_checkins WHERE worker_id=? AND reporting_date=?",
        (config["WORKER_ID"], today),
    ).fetchone()
    unfinished = connection.execute(
        """SELECT 1 FROM runs r JOIN reporters p ON p.id=r.reporter_id
        WHERE r.expected_date<=? AND r.state IN ('pending','running','retry_wait')
        AND p.deleted_at IS NULL""",
        (today,),
    ).fetchone()
    if not checked_in or unfinished:
        return None
    since = connection.execute(
        "SELECT covered_through FROM newsletter_state WHERE singleton=1"
    ).fetchone()[0]
    articles = [
        content.decode(row)
        for row in many(
            connection,
            """SELECT * FROM articles WHERE deleted_at IS NULL AND published_at>?
            ORDER BY published_at DESC,id DESC""",
            (since,),
        )
    ]
    failed = connection.execute(
        """SELECT 1 FROM runs r JOIN reporters p ON p.id=r.reporter_id
        WHERE r.expected_date=? AND r.state='failed' AND p.deleted_at IS NULL""",
        (today,),
    ).fetchone()
    connection.execute(
        """INSERT INTO newsletters (newsletter_date,article_ids_json,payload_json,created_at)
        VALUES (?,?,?,?)""",
        (
            today,
            v.canonical([article["id"] for article in articles]),
            message(config, today, articles, bool(failed)) if articles else None,
            clock.now(),
        ),
    )
    connection.execute(
        "UPDATE newsletter_state SET covered_through=? WHERE singleton=1",
        (clock.now(),),
    )
    return len(articles)


def message(config, day, articles, failed):
    base = config["BASE_URL"].rstrip("/")
    for article in articles:
        article["url"] = base + "/articles/" + article["id"]
    date = clock.long_date(day)
    count = f"{len(articles)} new article" + ("" if len(articles) == 1 else "s")
    values = {"articles": articles, "base": base, "date": date, "failed": failed}
    return v.canonical(
        {
            "from": config["EMAIL_FROM"],
            "to": [config["ALERT_TO"]],
            "subject": f"News · {date} · {count}",
            "html": templates.get_template("newsletter.html").render(values),
            "text": templates.get_template("newsletter.txt").render(values),
        }
    )


def deliver(config):
    """Send saved newsletters outside transactions; returns how many Resend accepted."""
    if not configured(config):
        return 0
    window = clock.now() - notifications.SAFE_WINDOW
    with transaction(config["DATABASE"], write=True) as connection:
        connection.execute(
            """UPDATE newsletters SET error=? WHERE payload_json IS NOT NULL
            AND sent_at IS NULL AND started_at<=?""",
            (notifications.UNCERTAIN, window),
        )
        due = many(
            connection,
            """SELECT newsletter_date,payload_json,started_at FROM newsletters
            WHERE payload_json IS NOT NULL AND sent_at IS NULL
            AND (retry_at IS NULL OR retry_at<=?) AND (started_at IS NULL OR started_at>?)
            ORDER BY newsletter_date""",
            (clock.now(), window),
        )
        for row in due:
            connection.execute(
                """UPDATE newsletters SET started_at=coalesce(started_at,?),
                attempts=attempts+1,retry_at=? WHERE newsletter_date=?""",
                (clock.now(), clock.now() + RETRY_SECONDS, row["newsletter_date"]),
            )
    sent = 0
    for row in due:
        receipt, error, refused = notifications.post(
            config, row["payload_json"], "news-newsletter/" + row["newsletter_date"]
        )
        with transaction(config["DATABASE"], write=True) as connection:
            if error:
                # A refused first attempt sent nothing, so its window restarts.
                connection.execute(
                    """UPDATE newsletters SET error=?,started_at=
                    CASE WHEN ? THEN NULL ELSE started_at END WHERE newsletter_date=?""",
                    (error, refused and row["started_at"] is None, row["newsletter_date"]),
                )
            else:
                connection.execute(
                    """UPDATE newsletters SET sent_at=?,receipt_id=?,error=NULL,
                    retry_at=NULL WHERE newsletter_date=?""",
                    (clock.now(), receipt, row["newsletter_date"]),
                )
                sent += 1
    return sent
