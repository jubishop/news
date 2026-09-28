"""News server: public reading, owner newsroom, and a separate worker API."""

import os
import sys

if sys.version_info[:2] != (3, 14):
    raise RuntimeError("News requires Python 3.14.")

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from . import auth, clock, incidents
from .db import transaction
from .errors import Problem


def create_app(settings=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.environ.get("NEWS_DATABASE", "var/news.sqlite3"),
        SECRET_KEY=os.environ.get("NEWS_SECRET_KEY", ""),
        BASE_URL=os.environ.get("NEWS_BASE_URL", "https://news.jubishop.com"),
        ACCESS_ISSUER=os.environ.get(
            "NEWS_ACCESS_ISSUER", "https://jubishop.cloudflareaccess.com"
        ),
        OWNER_AUD=os.environ.get("NEWS_OWNER_AUD", ""),
        WORKER_AUD=os.environ.get("NEWS_WORKER_AUD", ""),
        OWNER_EMAIL=os.environ.get("NEWS_OWNER_EMAIL", ""),
        WORKER_ID=os.environ.get("NEWS_WORKER_ID", "local"),
        MONITOR_WORKER=os.environ.get("NEWS_MONITOR_WORKER", "false").lower() == "true",
        MONITOR_START_DATE=os.environ.get("NEWS_MONITOR_START_DATE"),
        EMAIL_FROM=os.environ.get("NEWS_EMAIL_FROM", "News <news@jubishop.com>"),
        ALERT_TO=os.environ.get("NEWS_ALERT_TO", ""),
        RESEND_API_KEY=os.environ.get("RESEND_API_KEY", ""),
        BACKUP_STATE=os.environ.get(
            "NEWS_BACKUP_STATE", "/var/lib/news-backup/size.json"
        ),
        MAX_CONTENT_LENGTH=2_000_000,
        MAX_FORM_MEMORY_SIZE=300_000,
        SESSION_COOKIE_NAME="news_session",
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=12 * 3600,
    )
    if settings:
        app.config.update(settings)
    if len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError(
            "Set NEWS_SECRET_KEY to a private random value of at least 32 characters."
        )
    if (
        not app.config["OWNER_AUD"]
        or not app.config["WORKER_AUD"]
        or not app.config["OWNER_EMAIL"]
    ):
        raise RuntimeError(
            "Configure the separate owner and worker Access applications and owner email."
        )
    if app.config["OWNER_AUD"] == app.config["WORKER_AUD"]:
        raise RuntimeError("Owner and worker audiences must be different.")
    if app.config["MONITOR_WORKER"] and not app.config["MONITOR_START_DATE"]:
        raise RuntimeError(
            "Set NEWS_MONITOR_START_DATE before enabling worker monitoring."
        )
    if app.config["MONITOR_START_DATE"]:
        from .validation import calendar_date

        calendar_date(app.config["MONITOR_START_DATE"], "NEWS_MONITOR_START_DATE")
    auth.configure(app)
    from .routes import pages, api
    from .cli import register

    app.register_blueprint(pages)
    app.register_blueprint(api, url_prefix="/api/v1/worker")
    register(app)

    @app.before_request
    def authorization():
        if request.path == "/newsroom" or request.path.startswith("/newsroom/"):
            auth.require("owner")
        elif request.path == "/api" or request.path.startswith("/api/"):
            auth.require("worker")

    @app.after_request
    def headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src https:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(Problem)
    def problem(error):
        if error.incident:
            with transaction(app.config["DATABASE"], write=True) as connection:
                incidents.observe(connection, **error.incident)
        if request.path.startswith("/api/") or request.path.endswith(
            "/schedule-preview"
        ):
            return jsonify(error=error.code, message=str(error)), error.status
        return render_template(
            "error.html", message=str(error), status=error.status
        ), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith("/api/"):
            return jsonify(
                error=error.name.lower().replace(" ", "_"), message=error.description
            ), error.code
        return render_template(
            "error.html", message=error.description, status=error.code
        ), error.code

    app.jinja_env.filters["event_time"] = clock.display_time
    app.jinja_env.globals.update(pacific_today=clock.today)
    return app
