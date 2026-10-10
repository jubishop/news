"""Bounded, explicit input contracts; editorial meaning belongs to the worker."""

from datetime import date
import json
import re
from urllib.parse import urlsplit

from .errors import Problem


def text(value, name, limit, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise Problem(f"{name} must be text of at most {limit:,} characters.")
    value = value.strip()
    if not value and not empty:
        raise Problem(f"{name} is required.")
    return value


def identifier(value, name="request_id"):
    value = text(value, name, 128)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise Problem(
            f"{name} must contain only letters, numbers, underscores, or hyphens."
        )
    return value


def calendar_date(value, name):
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError()
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError()
        return result
    except ValueError:
        raise Problem(f"{name} must be a YYYY-MM-DD date.") from None


def url(value, *, image=False):
    if not isinstance(value, str) or not value or len(value) > 4096:
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in (("https",) if image else ("https", "http"))
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not any(ord(c) < 32 or c.isspace() for c in value)
        )
    except ValueError:
        return False


def object_fields(value, allowed, required):
    if (
        not isinstance(value, dict)
        or set(value) - set(allowed)
        or set(required) - set(value)
    ):
        raise Problem("Missing or unsupported fields.", code="invalid_fields")


def lead_image(value):
    fields = ("url", "alt", "credit", "credit_url")
    object_fields(value, fields, fields)
    if not url(value["url"], image=True) or not url(value["credit_url"]):
        raise Problem("Lead images need an HTTPS image URL and an HTTP or HTTPS credit URL.")
    return {
        "url": value["url"],
        "alt": text(value["alt"], "lead image alt text", 300),
        "credit": text(value["credit"], "lead image credit", 200),
        "credit_url": value["credit_url"],
    }


def article(value):
    fields = (
        "title",
        "summary",
        "body_markdown",
        "article_date",
        "coverage_start",
        "coverage_end",
        "sources",
    )
    object_fields(value, (*fields, "lead_image"), fields)
    result = {
        name: text(value[name], name, maximum)
        for name, maximum in [
            ("title", 300),
            ("summary", 2000),
            ("body_markdown", 250_000),
        ]
    }
    for name in ("article_date", "coverage_start", "coverage_end"):
        result[name] = calendar_date(value[name], name).isoformat()
    if result["coverage_end"] < result["coverage_start"]:
        raise Problem("Coverage end must be on or after coverage start.")
    if not isinstance(value["sources"], list) or len(value["sources"]) > 100:
        raise Problem("Sources must be a list of at most 100 items.")
    result["sources"] = []
    for source in value["sources"]:
        object_fields(source, ("title", "url"), ("title", "url"))
        if not url(source["url"]):
            raise Problem("Sources need absolute HTTP or HTTPS URLs.")
        result["sources"].append(
            {"title": text(source["title"], "source title", 500), "url": source["url"]}
        )
    # Optional so earlier workers and saved results stay valid; null means none.
    if value.get("lead_image") is not None:
        result["lead_image"] = lead_image(value["lead_image"])
    return result


def canonical(value):
    try:
        serialized = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        serialized.encode("utf-8")
        return serialized
    except (ValueError, TypeError, RecursionError):
        raise Problem("Send a valid, bounded JSON value.") from None


def integer(value, name, low, high):
    try:
        result = int(value)
        if str(result) != str(value) or not low <= result <= high:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise Problem(f"{name} must be a whole number from {low} to {high}.") from None
