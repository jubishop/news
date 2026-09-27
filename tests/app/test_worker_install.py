"""Cron entry generation and OS crontab boundary."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from news.worker_install import install


class CronTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="news cron ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root / "worker.json"
        self.config.write_text(json.dumps({"state_dir": str(self.root / "state"), "codex": "/mock/codex"}))
        self.config.chmod(0o600)
        (self.root / ".venv/bin").mkdir(parents=True)
        (self.root / ".venv/bin/python").touch()
        self.crontab = "MAILTO=owner@example.com\n17 3 * * * /existing/backup\n"
        self.calls = []
        self.enterContext(patch("news.worker_install.subprocess.run", side_effect=self.command))
        self.readlink = os.readlink
        self.enterContext(patch("os.readlink", side_effect=lambda path, *args, **kwargs: "/var/db/timezone/zoneinfo/America/Los_Angeles" if str(path) == "/etc/localtime" else self.readlink(path, *args, **kwargs)))

    def command(self, args, **kwargs):
        self.calls.append(args)
        if args == ["crontab", "-l"]:
            return subprocess.CompletedProcess(args, 0, self.crontab, "")
        if args == ["crontab", "-"]:
            self.crontab = kwargs["input"]
        return subprocess.CompletedProcess(args, 0, "", "")

    def test_preview_does_not_install_and_quotes_absolute_paths(self):
        entry = install(self.config, self.root)
        self.assertTrue(entry.startswith("0 6 * * * "))
        self.assertIn("news.worker", entry)
        self.assertIn("'" + str(self.config.resolve()) + "'", entry)
        self.assertNotIn(["crontab", "-"], self.calls)

    def test_install_is_idempotent_and_preserves_other_cron_jobs(self):
        install(self.config, self.root, apply=True)
        installed = self.crontab
        install(self.config, self.root, apply=True)
        self.assertEqual(self.crontab, installed)
        self.assertIn("17 3 * * * /existing/backup", self.crontab)
        self.assertIn("MAILTO=owner@example.com", self.crontab)
        self.assertEqual(self.crontab.count("# news-reporting-worker"), 1)
        self.assertIn("0 6 * * *", self.crontab)

    def test_wrong_system_timezone_is_rejected_before_install(self):
        with patch("os.readlink", side_effect=lambda path, *args, **kwargs: "/usr/share/zoneinfo/UTC" if str(path) == "/etc/localtime" else self.readlink(path, *args, **kwargs)):
            with self.assertRaisesRegex(Exception, "Pacific"):
                install(self.config, self.root, apply=True)
        self.assertNotIn(["crontab", "-"], self.calls)

    def test_crontab_read_error_never_replaces_existing_jobs(self):
        with patch("news.worker_install.subprocess.run", return_value=subprocess.CompletedProcess(["crontab", "-l"], 1, "", "permission denied")):
            with self.assertRaisesRegex(Exception, "crontab"):
                install(self.config, self.root, apply=True)
        self.assertNotIn(["crontab", "-"], self.calls)
