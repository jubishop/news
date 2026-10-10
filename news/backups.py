"""Encrypted snapshots and isolated restore checks, independent of the worker."""

from contextlib import contextmanager, closing
import fcntl
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

from . import clock, incidents, r2
from .db import transaction

THRESHOLD = 1_000_000_000


@contextmanager
def workspace(config):
    directory = Path(config["BACKUP_STATE"]).parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / "backup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield directory


def restic(*args):
    # Do not expose provider errors, repository URLs, or credentials in the journal.
    subprocess.run(
        ["restic", *args],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=3600,
    )


def backup(config):
    with workspace(config) as directory:
        dump = directory / "news.sqlite3"
        try:
            descriptor = os.open(dump, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.close(descriptor)
            os.chmod(dump, 0o600)
            with closing(
                sqlite3.connect(
                    Path(config["DATABASE"]).resolve().as_uri() + "?mode=ro", uri=True
                )
            ) as source:
                with closing(sqlite3.connect(dump)) as destination:
                    source.backup(destination)
                    destination.execute("PRAGMA journal_mode=DELETE")
            restic(
                "backup", "--host", "news-server", "--tag", "news", str(dump.resolve())
            )
            restic(
                "forget",
                "--host",
                "news-server",
                "--tag",
                "news",
                "--group-by",
                "host",
                "--keep-daily",
                "7",
                "--keep-weekly",
                "4",
                "--prune",
            )
            url = r2.bucket_url()
            size, objects = r2.list_bucket(
                url,
                r2.setting("AWS_ACCESS_KEY_ID"),
                r2.setting("AWS_SECRET_ACCESS_KEY"),
            )
            state = {
                "bucket": url,
                "bytes": size,
                "objects": objects,
                "checked_at": clock.now(),
            }
            r2.save(Path(config["BACKUP_STATE"]), state)
            with transaction(config["DATABASE"], write=True) as connection:
                if size > THRESHOLD:
                    incidents.observe(
                        connection,
                        "backup-storage",
                        "backup_storage",
                        f"News backup storage uses {size:,} bytes across {objects:,} objects, above 1 GB "
                        "(1,000,000,000 bytes). Backups continue with seven daily and four weekly snapshots. "
                        "This measures the News bucket, not account-wide spending or incomplete uploads.",
                    )
                elif size < THRESHOLD:
                    incidents.resolve(connection, "backup-storage")
            return state
        finally:
            dump.unlink(missing_ok=True)


def restore_check(config):
    with workspace(config) as directory:
        restic("check", "--read-data")
        with tempfile.TemporaryDirectory(prefix="restore-", dir=directory) as temporary:
            restic(
                "restore",
                "latest",
                "--host",
                "news-server",
                "--tag",
                "news",
                "--target",
                temporary,
            )
            matches = list(Path(temporary).rglob("news.sqlite3"))
            if len(matches) != 1:
                raise ValueError("The restored snapshot must contain one database.")
            with closing(
                sqlite3.connect(matches[0].as_uri() + "?mode=ro", uri=True)
            ) as connection:
                if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("Restored database failed integrity validation.")
                if connection.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Restored database has invalid references.")
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (1, 2, 3):
                    raise ValueError("Restored database schema version is unsupported.")
                for table in (
                    "reporters",
                    "runs",
                    "run_attempts",
                    "articles",
                    "worker_checkins",
                    "incidents",
                ):
                    connection.execute("SELECT count(*) FROM " + table).fetchone()
                if version >= 2:
                    connection.execute("SELECT version FROM archive_state WHERE singleton=1").fetchone()
                    connection.execute("SELECT revision FROM articles LIMIT 1").fetchone()
                if version >= 3:
                    connection.execute("SELECT lead_image_json FROM articles LIMIT 1").fetchone()
            state = {"checked_at": clock.now(), "ok": True}
            r2.save(directory / "restore.json", state)
            return state
