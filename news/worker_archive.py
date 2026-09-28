"""Versioned archive downloads and atomic, recoverable local cache generations."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from . import validation as v
from .worker_io import APIError, WorkerError, read_json, save_json, sync_directory

ARTICLE_FIELDS = ("title", "summary", "body_markdown", "article_date", "coverage_start", "coverage_end", "sources")
SUMMARY_FIELDS = ("id", "title", "summary", "article_date", "coverage_start", "coverage_end")


class ArchiveChanged(WorkerError):
    pass


def revision(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise WorkerError("News API returned an invalid archive revision.")
    return value


def page(api, number=1, version=None, total=None, limit=100):
    route = f"/articles/manifest?page={number}&limit={limit}"
    if version is not None:
        route += "&version=" + version
    result = api.call(route)
    if (not isinstance(result.get("articles"), list)
            or type(result.get("total")) is not int or not 0 <= result["total"] <= 10_000_000
            or type(result.get("page")) is not int or result["page"] != number
            or type(result.get("limit")) is not int or result["limit"] != limit
            or type(result.get("has_more")) is not bool
            or result["has_more"] != (number * limit < result["total"])
            or len(result["articles"]) != min(limit, max(0, result["total"] - (number - 1) * limit))):
        raise WorkerError("News API returned an incomplete or invalid archive manifest.")
    revision(result.get("version"))
    if version is not None and (result["version"] != version or result["total"] != total):
        raise ArchiveChanged("The article archive changed during synchronization.")
    return result


def render(raw, identity, expected):
    reporter = v.identifier(raw["reporter_id"], "reporter id")
    if raw["id"] != identity or reporter != raw["reporter_id"] or raw.get("deleted_at") is not None:
        raise WorkerError("News API returned an invalid archive article.")
    if raw.get("revision") != expected:
        raise ArchiveChanged("An archive article changed during download.")
    article = v.article({key: raw[key] for key in ARTICLE_FIELDS})
    name = v.text(raw.get("reporter_name", reporter), "reporter name", 120)
    metadata = {"id": identity, "reporter_id": reporter, "reporter_name": name,
                **{key: article[key] for key in ("article_date", "coverage_start", "coverage_end")}}
    text = "# " + article["title"] + "\n\n" + "\n".join(f"{key}: {value}" for key, value in metadata.items())
    text += "\n\n## Summary\n\n" + article["summary"] + "\n\n## Article\n\n" + article["body_markdown"]
    text += "\n\n## Sources\n\n" + "\n".join(f'- {source["title"]}: {source["url"]}' for source in article["sources"]) + "\n"
    entry = {"revision": expected, "reporter_id": reporter,
             "summary": {"id": identity, **{key: article[key] for key in SUMMARY_FIELDS if key != "id"}}}
    entry["digest"] = digest(entry, text)
    return entry, text


def digest(entry, text):
    data = [entry["revision"], entry["reporter_id"], entry["summary"], text]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class ArchiveCache:
    def __init__(self, root):
        self.root = root
        self.path = Path(tempfile.mkdtemp(prefix="generation-", dir=root))
        self.previous = root / "current"
        self.committed = False
        self.summaries = {}
        self.snapshot = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if not self.committed:
            shutil.rmtree(self.path)

    def synchronize(self, api):
        try:
            cached = read_json(self.previous / "cache.json")
            cached = cached["articles"] if cached["format"] == 1 else {}
            if not isinstance(cached, dict):
                cached = {}
        except (OSError, ValueError, KeyError, TypeError):
            cached = {}
        for attempt in range(3):
            try:
                self.download(api, cached)
                self.copy_index()
                return
            except (ArchiveChanged, APIError) as exc:
                if isinstance(exc, APIError) and exc.status not in (404, 409):
                    raise
                if attempt == 2:
                    raise WorkerError("Article archive kept changing during synchronization; retry the batch. Previous cache retained.") from exc
                shutil.rmtree(self.path / "articles")

    def download(self, api, cached):
        articles = self.path / "articles"
        articles.mkdir(mode=0o700)
        records, summaries = {}, {}
        first = current = page(api)
        version, total = first["version"], first["total"]
        while True:
            for item in current["articles"]:
                identity = v.identifier(item["id"], "article id")
                if identity != item["id"]:
                    raise WorkerError("News API returned an invalid article ID.")
                expected = revision(item["revision"])
                if identity in records:
                    raise ArchiveChanged("News API repeated an archive article.")
                entry, source = cached.get(identity), self.previous / "articles" / f"{identity}.md"
                text = None
                if isinstance(entry, dict) and entry.get("revision") == expected:
                    try:
                        text = source.read_bytes().decode("utf-8")
                        if entry["summary"]["id"] != identity or entry["digest"] != digest(entry, text):
                            text = None
                    except (OSError, ValueError, KeyError, TypeError):
                        text = None
                if text is None:
                    entry, text = render(api.call(f"/articles/{identity}?version={version}"), identity, expected)
                target = articles / f"{identity}.md"
                if source.is_file() and source.read_bytes() == text.encode():
                    os.link(source, target)
                else:
                    target.write_text(text, encoding="utf-8")
                    target.chmod(0o600)
                records[identity] = entry
                recent = summaries.setdefault(entry["reporter_id"], [])
                if len(recent) < 20:
                    recent.append(entry["summary"])
            if not current["has_more"]:
                break
            current = page(api, current["page"] + 1, version, total)
        # Even an unchanged or empty archive needs a final guard before promotion.
        final = page(api, version=version, total=total, limit=1)
        if len(records) != total or final["articles"] != first["articles"][:1]:
            raise ArchiveChanged("News API returned an inconsistent archive manifest.")
        save_json(self.path / "cache.json", {"format": 1, "articles": records})
        self.summaries = summaries
        self.snapshot = {"retrieved_at": datetime.now(timezone.utc).isoformat(),
                         "article_count": total, "archive_version": version}

    def copy_index(self):
        source = self.previous / "index.sqlite"
        if not source.exists() and not self.previous.exists():
            source = self.root / "index.sqlite"  # One-time upgrade from the original cache.
        if source.exists():
            try:
                with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as old:
                    with closing(sqlite3.connect(self.path / "index.sqlite")) as new:
                        old.backup(new)
            except sqlite3.DatabaseError:
                (self.path / "index.sqlite").unlink(missing_ok=True)

    def publish(self):
        save_json(self.path / "snapshot.json", self.snapshot)
        # Persist new files and QMD's SQLite sidecars before the single pointer switch.
        for directory, _, files in os.walk(self.path):
            for name in files:
                with (Path(directory) / name).open("rb") as stream:
                    os.fsync(stream.fileno())
            sync_directory(directory)
        pointer = self.root / "next"
        pointer.unlink(missing_ok=True)
        pointer.symlink_to(self.path.name, target_is_directory=True)
        os.replace(pointer, self.root / "current")
        self.committed = True
        sync_directory(self.root)
        for old in self.root.glob("generation-*"):
            if old != self.path and old.is_dir() and not old.is_symlink():
                shutil.rmtree(old)
        for name in ("articles", "config", "index.sqlite", "index.sqlite-wal", "index.sqlite-shm", "snapshot.json"):
            old = self.root / name
            if old.is_dir() and not old.is_symlink():
                shutil.rmtree(old)
            else:
                old.unlink(missing_ok=True)
