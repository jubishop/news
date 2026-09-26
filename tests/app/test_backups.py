"""Real SQLite snapshots; fakes only at Restic and HTTP boundaries."""

import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from unittest.mock import patch
from urllib.parse import urlsplit

from support import ServerFixture


def listing(sizes, token=None):
    return (
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        + "".join(f"<Contents><Size>{size}</Size></Contents>" for size in sizes)
        + f"<IsTruncated>{str(bool(token)).lower()}</IsTruncated>"
        + (f"<NextContinuationToken>{token}</NextContinuationToken>" if token else "")
        + "</ListBucketResult>"
    ).encode()


class BackupTests(ServerFixture):
    def setUp(self):
        super().setUp()
        self.workspace = Path(self.database).parent / "backups"
        self.app.config.update(
            BACKUP_STATE=str(self.workspace / "size.json"),
            RESEND_API_KEY="fixture",
            ALERT_TO="owner@example.com",
        )
        self.enterContext(
            patch.dict(
                os.environ,
                {
                    "RESTIC_REPOSITORY": "s3:https://fixture.r2.cloudflarestorage.com/news-backups",
                    "RESTIC_PASSWORD": "fixture",
                    "AWS_ACCESS_KEY_ID": "fixture",
                    "AWS_SECRET_ACCESS_KEY": "fixture",
                },
            )
        )
        self.commands = []
        self.sent = []
        self.pages = []
        self.snapshot = self.workspace.parent / "remote-snapshot.sqlite3"
        self.enterContext(patch("subprocess.run", side_effect=self.restic))
        self.http.side_effect = self.request

    def restic(self, args, **kwargs):
        self.commands.append(args)
        self.assertEqual(args[0], "restic")
        self.assertTrue(kwargs.get("check"))
        if args[1] == "backup":
            dump = Path(args[-1])
            with sqlite3.connect(dump) as db:
                self.assertEqual(
                    db.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
                self.assertEqual(
                    db.execute("SELECT count(*) FROM reporters").fetchone()[0], 1
                )
            self.assertEqual(dump.stat().st_mode & 0o777, 0o600)
            shutil.copyfile(dump, self.snapshot)
        if args[1] == "restore":
            destination = (
                Path(args[args.index("--target") + 1]) / "restored/news.sqlite3"
            )
            destination.parent.mkdir(parents=True)
            shutil.copyfile(self.snapshot, destination)
        return subprocess.CompletedProcess(args, 0)

    def request(self, request, **kwargs):
        if urlsplit(request.full_url).hostname == "api.resend.com":
            self.sent.append(request)
            return io.BytesIO(b'{"id":"backup-warning"}')
        self.assertIn("AWS4-HMAC-SHA256", request.get_header("Authorization"))
        value = self.pages.pop(0)
        if isinstance(value, Exception):
            raise value
        return io.BytesIO(value)

    def backup(self, *pages):
        self.pages = list(pages)
        result = self.app.test_cli_runner().invoke(args=["backup"])
        self.assertEqual(result.exit_code, 0, result.output)

    def test_consistent_snapshot_retention_paginated_size_and_restore(self):
        self.reporter()
        self.backup(listing([100, 200], token="page2"), listing([30]))
        self.assertFalse((self.workspace / "news.sqlite3").exists())
        state = json.loads((self.workspace / "size.json").read_text())
        self.assertEqual(state["bytes"], 330)
        self.assertEqual(state["objects"], 3)
        forget = next(args for args in self.commands if args[1] == "forget")
        self.assertEqual(forget[forget.index("--keep-daily") + 1], "7")
        self.assertEqual(forget[forget.index("--keep-weekly") + 1], "4")
        self.assertIn("--prune", forget)
        result = self.app.test_cli_runner().invoke(args=["restore-check"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.sent, [])

    def test_size_warning_once_per_crossing_and_failure_preserves_size(self):
        self.reporter()
        self.backup(listing([1_000_000_001]))
        self.backup(listing([2_000_000_000]))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("1,000,000,001", json.loads(self.sent[0].data)["text"])
        state = (self.workspace / "size.json").read_text()
        self.pages = [listing([-1])]
        failed = self.app.test_cli_runner().invoke(args=["backup"])
        self.assertNotEqual(failed.exit_code, 0)
        self.assertEqual((self.workspace / "size.json").read_text(), state)
        self.assertFalse((self.workspace / "news.sqlite3").exists())
        self.backup(listing([1_000_000_000]))
        self.backup(listing([1_000_000_001]))
        warning_count = sum(
            "backup storage" in json.loads(req.data)["subject"] for req in self.sent
        )
        self.assertEqual(warning_count, 1)
        self.backup(listing([999]))
        self.backup(listing([1_000_000_002]))
        warning_count = sum(
            "backup storage" in json.loads(req.data)["subject"] for req in self.sent
        )
        self.assertEqual(warning_count, 2)

    def test_backup_failure_never_prunes_and_removes_temporary_dump(self):
        self.reporter()

        def fail(args, **kwargs):
            self.commands.append(args)
            raise subprocess.CalledProcessError(1, args)

        with patch("subprocess.run", side_effect=fail):
            result = self.app.test_cli_runner().invoke(args=["backup"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual([args[1] for args in self.commands], ["backup"])
        self.assertFalse((self.workspace / "news.sqlite3").exists())
