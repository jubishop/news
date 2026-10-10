"""Exercise the executable entry points used by systemd, without Flask's test runner."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class CommandTests(unittest.TestCase):
    def test_initialize_maintain_and_gunicorn_entry_points(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "news.sqlite3")
            env = dict(
                os.environ,
                NEWS_DATABASE=database,
                NEWS_SECRET_KEY="fixture-only-secret-at-least-32-characters",
                NEWS_OWNER_AUD="owner-fixture",
                NEWS_WORKER_AUD="worker-fixture",
                NEWS_OWNER_EMAIL="fixture@example.com",
                NEWS_MONITOR_WORKER="false",
                NEWS_ALERT_TO="",
                RESEND_API_KEY="",
            )
            for command in ("init-db", "init-db", "maintain"):
                result = subprocess.run(
                    [sys.executable, "-B", "-m", "news.cli", command],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with sqlite3.connect(database) as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0], 3
                )
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "gunicorn",
                    "--check-config",
                    "news:create_app()",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
