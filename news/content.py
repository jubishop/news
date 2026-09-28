"""Stored articles, bounded search, safe Markdown, and 30-day Trash."""

import json
import re

from markdown_it import MarkdownIt
from markupsafe import Markup

from . import clock, validation as v
from .db import one, many
from .errors import Problem

TRASH_SECONDS = 30 * 24 * 3600


def render_markdown(source):
    renderer = MarkdownIt("commonmark", {"html": False, "maxNesting": 30}).enable(
        "table"
    )
    renderer.validateLink = lambda value: bool(v.url(value))

    def image(tokens, index, options, env):
        token = tokens[index]
        if not v.url(token.attrGet("src"), image=True):
            return renderer.utils.escapeHtml(token.content)
        token.attrSet("loading", "lazy")
        token.attrSet("decoding", "async")
        token.attrSet("referrerpolicy", "no-referrer")
        return renderer.renderer.image(tokens, index, options, env)

    renderer.renderer.rules["image"] = image
    return Markup(renderer.render(source))


def decode(row):
    if row:
        row["sources"] = json.loads(row.pop("sources_json"))
    return row


def article(connection, identity):
    row = one(
        connection,
        "SELECT * FROM articles WHERE id=? AND deleted_at IS NULL",
        (identity,),
    )
    if not row:
        raise Problem("Article not found.", 404, "not_found")
    return decode(row)


def archive_version(connection, expected=None):
    if expected is not None and not re.fullmatch(r"[0-9a-f]{32}", expected):
        raise Problem("Invalid archive version.")
    version = connection.execute("SELECT version FROM archive_state WHERE singleton=1").fetchone()[0]
    if expected is not None and expected != version:
        raise Problem("The article archive changed. Restart synchronization.", 409, "archive_changed")
    return version


def manifest(connection, params):
    limit = v.integer(params.get("limit", 100), "limit", 1, 100)
    page = v.integer(params.get("page", 1), "page", 1, 100_000)
    if page > 1 and "version" not in params:
        raise Problem("Archive version is required after the first page.")
    version = archive_version(connection, params.get("version"))
    total = connection.execute("SELECT count(*) FROM articles WHERE deleted_at IS NULL").fetchone()[0]
    rows = many(connection, """SELECT id,revision FROM articles WHERE deleted_at IS NULL
                ORDER BY published_at DESC,id DESC LIMIT ? OFFSET ?""", (limit, (page - 1) * limit))
    return {"articles": rows, "version": version, "page": page, "limit": limit,
            "total": total, "has_more": page * limit < total}


def search(connection, params):
    limit = v.integer(params.get("limit", 30), "limit", 1, 100)
    page = v.integer(params.get("page", 1), "page", 1, 100_000)
    clauses, args = ["deleted_at IS NULL"], []
    reporter_id = params.get("reporter_id")
    if reporter_id:
        clauses.append("reporter_id=?")
        args.append(v.identifier(reporter_id, "reporter_id"))
    query = v.text(params.get("q", ""), "Search", 300, empty=True)
    if query:
        clauses.append(
            "(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' OR body_markdown LIKE ? ESCAPE '\\')"
        )
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        args.extend(["%" + escaped + "%"] * 3)
    for key, column, operator in [
        ("coverage_start", "coverage_end", ">="),
        ("coverage_end", "coverage_start", "<="),
    ]:
        if params.get(key):
            clauses.append(column + operator + "?")
            args.append(v.calendar_date(params[key], key).isoformat())
    if (
        params.get("coverage_start")
        and params.get("coverage_end")
        and params["coverage_end"] < params["coverage_start"]
    ):
        raise Problem("Coverage end must be on or after coverage start.")
    where = " AND ".join(clauses)
    total = connection.execute(
        "SELECT count(*) FROM articles WHERE " + where, args
    ).fetchone()[0]
    rows = many(
        connection,
        "SELECT * FROM articles WHERE "
        + where
        + " ORDER BY published_at DESC,id DESC LIMIT ? OFFSET ?",
        (*args, limit, (page - 1) * limit),
    )
    return {
        "articles": [decode(row) for row in rows],
        "page": page,
        "limit": limit,
        "total": total,
        "has_more": page * limit < total,
    }


def change_state(connection, identity, action):
    row = one(connection, "SELECT id,deleted_at FROM articles WHERE id=?", (identity,))
    if not row:
        raise Problem("Article not found.", 404, "not_found")
    if action == "delete":
        connection.execute(
            "UPDATE articles SET deleted_at=? WHERE id=? AND deleted_at IS NULL",
            (clock.now(), identity),
        )
    elif action == "restore":
        if (
            row["deleted_at"] is not None
            and row["deleted_at"] + TRASH_SECONDS <= clock.now()
        ):
            raise Problem(
                "The 30-day restoration period has ended.", 409, "restore_expired"
            )
        connection.execute(
            "UPDATE articles SET deleted_at=NULL WHERE id=?", (identity,)
        )
    else:
        raise Problem("Unknown article action.", 404, "not_found")


def purge(connection):
    return connection.execute(
        "DELETE FROM articles WHERE deleted_at IS NOT NULL AND deleted_at<=?",
        (clock.now() - TRASH_SECONDS,),
    ).rowcount
