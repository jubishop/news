"""HTTP adaptation; state transitions live in the domain modules."""

from datetime import timedelta
import json
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from . import calendar_view, clock, content, contractors, jobs, reporters, schedules, validation as v
from .db import many, one, transaction
from .errors import Problem

pages = Blueprint("pages", __name__)
api = Blueprint("worker", __name__)


def database():
    return current_app.config["DATABASE"]


def body():
    if not request.is_json:
        raise Problem("Send application/json.", 415, "json_required")
    data = request.get_json()
    if not isinstance(data, dict):
        raise Problem("Send a JSON object.")
    return data


@pages.get("/")
def feed():
    with transaction(database()) as connection:
        results = content.search(connection, request.args)
        bylines = many(
            connection,
            """SELECT DISTINCT r.id,r.name FROM reporters r
            JOIN articles a ON a.reporter_id=r.id WHERE a.deleted_at IS NULL ORDER BY r.name,r.id""",
        )
        overdue = connection.execute(
            """SELECT count(*) FROM runs r JOIN reporters p ON p.id=r.reporter_id
            WHERE expected_date<? AND state IN ('pending','running','retry_wait') AND p.deleted_at IS NULL""",
            (clock.today().isoformat(),),
        ).fetchone()[0]
    return render_template("feed.html", **results, bylines=bylines, overdue=overdue)


@pages.get("/articles/<identity>")
def article(identity):
    with transaction(database()) as connection:
        row = content.article(connection, identity)
    return render_template(
        "article.html",
        article=row,
        article_html=content.render_markdown(row["body_markdown"]),
    )


@pages.get("/health")
def health():
    with transaction(database()) as connection:
        connection.execute("SELECT id FROM reporters LIMIT 1").fetchone()
    return jsonify(ok=True)


@pages.get("/newsroom")
def newsroom():
    archived = request.args.get("view") == "archive"
    with transaction(database()) as connection:
        calendar = calendar_view.month_view(connection, request.args.get("month"))
        condition = (
            "(deleted_at IS NOT NULL OR completed_at IS NOT NULL)"
            if archived
            else "(deleted_at IS NULL AND completed_at IS NULL)"
        )
        roster = [
            reporters.get(connection, row["id"])
            for row in many(
                connection,
                "SELECT id FROM reporters WHERE " + condition + " ORDER BY name,id",
            )
        ]
        for reporter in roster:
            reporter["last_run"] = one(
                connection,
                "SELECT * FROM runs WHERE reporter_id=? ORDER BY expected_date DESC,id DESC LIMIT 1",
                (reporter["id"],),
            )
            reporter["late"] = bool(
                connection.execute(
                    "SELECT 1 FROM runs WHERE reporter_id=? AND expected_date<? AND state IN ('pending','running','retry_wait')",
                    (reporter["id"], clock.today().isoformat()),
                ).fetchone()
            )
        alerts = many(
            connection,
            "SELECT * FROM incidents WHERE resolved_at IS NULL ORDER BY first_seen_at DESC LIMIT 100",
        )
        latest = one(
            connection,
            "SELECT * FROM worker_checkins ORDER BY received_at DESC LIMIT 1",
        )
        counts = {
            table: connection.execute("SELECT count(*) FROM " + table).fetchone()[0]
            for table in ("articles", "runs")
        }
        counts["articles"] = connection.execute(
            "SELECT count(*) FROM articles WHERE deleted_at IS NULL"
        ).fetchone()[0]
    backup = None
    try:
        backup = json.loads(Path(current_app.config["BACKUP_STATE"]).read_text())
    except (OSError, ValueError):
        pass
    return render_template(
        "newsroom.html",
        calendar=calendar,
        reporters=roster,
        archived=archived,
        alerts=alerts,
        latest=latest,
        counts=counts,
        backup=backup,
        monitoring=current_app.config["MONITOR_WORKER"],
    )


@pages.get("/newsroom/reporters/new")
def new_reporter():
    return render_template(
        "reporter.html",
        reporter=None,
        runs=[],
        articles=[],
        weekdays=schedules.WEEKDAYS,
        tomorrow=(clock.today() + timedelta(days=1)).isoformat(),
    )


@pages.get("/newsroom/reporters/<identity>")
def reporter_detail(identity):
    articles_page = v.integer(
        request.args.get("articles_page", 1), "articles_page", 1, 100_000
    )
    page = v.integer(request.args.get("page", 1), "page", 1, 100_000)
    with transaction(database()) as connection:
        reporter = reporters.get(connection, identity)
        runs = many(
            connection,
            "SELECT * FROM runs WHERE reporter_id=? ORDER BY expected_date DESC,id DESC LIMIT 30 OFFSET ?",
            (identity, (page - 1) * 30),
        )
        for run in runs:
            run["late"] = jobs.late(run)
            run["attempts"] = many(
                connection,
                """SELECT attempt_number,started_at,finished_at,outcome,
                reason,error_code,error_message,config_snapshot_json FROM run_attempts WHERE run_id=? ORDER BY attempt_number""",
                (run["id"],),
            )
            for attempt in run["attempts"]:
                attempt["snapshot"] = json.loads(attempt.pop("config_snapshot_json"))
        contractors.annotate_history(connection, reporter, runs)
        article_results = content.search(
            connection, {"reporter_id": identity, "limit": 20, "page": articles_page}
        )
        articles = article_results["articles"]
    return render_template(
        "reporter.html",
        reporter=reporter,
        runs=runs,
        articles=articles,
        weekdays=schedules.WEEKDAYS,
        tomorrow=(clock.today() + timedelta(days=1)).isoformat(),
        history_page=page,
        articles_page=articles_page,
        articles_more=article_results["has_more"],
    )


@pages.post("/newsroom/reporters")
@pages.post("/newsroom/reporters/<identity>")
def save_reporter(identity=None):
    with transaction(database(), write=True) as connection:
        identity = reporters.save(connection, request.form, identity)
    flash("Reporter saved. New schedules take effect tomorrow.")
    return redirect(url_for("pages.reporter_detail", identity=identity), code=303)


@pages.post("/newsroom/reporters/<identity>/<action>")
def reporter_state(identity, action):
    with transaction(database(), write=True) as connection:
        reporters.change_state(connection, identity, action)
    flash(
        {
            "pause": "Reporter paused. Work already underway is still accepted.",
            "resume": "Reporter resumed.",
            "delete": "Reporter removed. Its articles stay published.",
        }[action]
    )
    return redirect(
        url_for("pages.newsroom")
        if action == "delete"
        else url_for("pages.reporter_detail", identity=identity),
        code=303,
    )


@pages.get("/newsroom/schedule-preview")
@pages.post("/newsroom/schedule-preview")
def preview():
    values = request.form if request.method == "POST" else request.args
    schedule = schedules.parse(values)
    with transaction(database()) as connection:
        reporter = (
            reporters.get(connection, values["reporter_id"])
            if values.get("reporter_id") else None
        )
    schedules.validate_change(schedule, reporter["schedule"] if reporter else None)
    tomorrow = clock.today() + timedelta(days=1)
    day = schedules.next_date(schedule, tomorrow)
    return jsonify(next_date=day.isoformat() if day else None, cadence_label=schedules.label(schedule))


@pages.get("/newsroom/trash")
def trash():
    page = v.integer(request.args.get("page", 1), "page", 1, 100_000)
    with transaction(database()) as connection:
        articles = many(
            connection,
            "SELECT * FROM articles WHERE deleted_at>? ORDER BY deleted_at DESC,id DESC LIMIT 30 OFFSET ?",
            (clock.now() - content.TRASH_SECONDS, (page - 1) * 30),
        )
    for article in articles:
        article["purge_at"] = article["deleted_at"] + content.TRASH_SECONDS
    return render_template("trash.html", articles=articles, page=page)


@pages.post("/newsroom/articles/<identity>/<action>")
def article_state(identity, action):
    with transaction(database(), write=True) as connection:
        content.change_state(connection, identity, action)
    flash(
        "Article moved to Trash for 30 days."
        if action == "delete"
        else "Article restored."
    )
    return redirect(url_for("pages.trash"), code=303)


@api.post("/check-ins")
def check_in():
    with transaction(database(), write=True) as connection:
        result = jobs.discover(connection, g.worker, body())
    return jsonify(result)


@api.post("/runs/<identity>/claim")
def claim(identity):
    with transaction(database(), write=True) as connection:
        result = jobs.claim(connection, identity, g.worker, body())
    return jsonify(result)


@api.post("/runs/<identity>/renew")
def renew(identity):
    with transaction(database(), write=True) as connection:
        result = jobs.renew(connection, identity, g.worker, body())
    return jsonify(result)


@api.post("/runs/<identity>/result")
def result(identity):
    with transaction(database(), write=True) as connection:
        receipt = jobs.result(connection, identity, g.worker, body())
    return jsonify(receipt)


@api.get("/reporters/<identity>/runs")
def history(identity):
    page = v.integer(request.args.get("page", 1), "page", 1, 100_000)
    limit = v.integer(request.args.get("limit", 30), "limit", 1, 100)
    with transaction(database()) as connection:
        reporter = reporters.get(connection, identity)
        total = connection.execute(
            "SELECT count(*) FROM runs WHERE reporter_id=?", (identity,)
        ).fetchone()[0]
        runs = many(
            connection,
            "SELECT * FROM runs WHERE reporter_id=? ORDER BY expected_date DESC,id DESC LIMIT ? OFFSET ?",
            (identity, limit, (page - 1) * limit),
        )
        for run in runs:
            run["late"] = jobs.late(run)
            run["attempts"] = many(
                connection,
                """SELECT id,attempt_number,started_at,finished_at,outcome,
                reason,error_code,error_message,retryable FROM run_attempts WHERE run_id=? ORDER BY attempt_number""",
                (run["id"],),
            )
        contractors.annotate_history(connection, reporter, runs)
    return jsonify(
        runs=runs, page=page, limit=limit, total=total, has_more=page * limit < total
    )


@api.get("/articles/search")
def search():
    with transaction(database()) as connection:
        result = content.search(connection, request.args)
    return jsonify(result)


@api.get("/articles/manifest")
def archive_manifest():
    with transaction(database()) as connection:
        result = content.manifest(connection, request.args)
    return jsonify(result)


@api.get("/articles/<identity>")
def archived_article(identity):
    with transaction(database()) as connection:
        if "version" in request.args:
            content.archive_version(connection, request.args["version"])
        result = content.article(connection, identity)
    return jsonify(result)
