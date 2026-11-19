"""bin/setup-application leaves the installed worker's environment alone while a batch runs from it."""

import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from news.worker import run
from news.worker_install import LABEL, definition


ROOT = Path(__file__).resolve().parents[2]


class SetupApplicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="news setup ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.state = self.root / "state"
        self.config = self.root / "worker.json"
        self.config.write_text(json.dumps({"state_dir": str(self.state), "claude": "/mock/claude"}))
        self.config.chmod(0o600)
        self.checkout = self.root / "checkout"
        for name in ("bin/setup-application", "news/setup_guard.py"):
            (self.checkout / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, self.checkout / name)
        # The real interpreter runs the version check and the guard; venv and module installs are simulated.
        self.python = self.root / "python3"
        self.python.write_text(f'''#!/bin/sh
set -eu
case "$1 ${{2-}}" in
"-m venv")
    if [ "$3" = --clear ]; then rm -rf .venv; fi
    mkdir -p .venv/bin
    cp "$0" .venv/bin/python ;;
"-m "*) ;;
*) exec "{sys.executable}" "$@" ;;
esac
''')
        self.python.chmod(0o755)
        self.marker = self.checkout / ".venv/old-environment"
        self.marker.parent.mkdir(parents=True)
        self.marker.touch()

    def install_worker(self, checkout):
        agent = self.home / "Library/LaunchAgents" / f"{LABEL}.plist"
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_bytes(definition(self.config, checkout, self.state))

    def hold_lock(self, path=None):
        path = path or self.state / "worker.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.open("a")
        self.addCleanup(lock.close)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock

    def setup(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith(("NEWS_", "PYTHON"))}
        return subprocess.run([str(self.checkout / "bin/setup-application")], cwd=self.root, capture_output=True,
                              text=True, env=env | {"HOME": str(self.home), "NEWS_PYTHON": str(self.python)})

    def assert_rebuilt(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertTrue((self.checkout / ".venv/bin/python").is_file())

    def test_refuses_while_a_batch_runs_from_this_checkout_and_rebuilds_once_it_ends(self):
        self.install_worker(self.checkout)
        lock = self.hold_lock()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("News worker is running from " + str(self.checkout.resolve()), result.stderr)
        self.assertTrue(self.marker.exists())
        self.assertFalse((self.checkout / ".venv/bin").exists())
        fcntl.flock(lock, fcntl.LOCK_UN)
        self.assert_rebuilt(self.setup())

    def test_rebuilds_the_worker_checkout_when_no_batch_holds_the_lock(self):
        self.install_worker(self.checkout)
        self.assert_rebuilt(self.setup())
        self.assertFalse((self.state / "worker.lock").exists())

    def test_other_checkouts_ignore_the_worker_lock(self):
        other = self.root / "permanent"
        other.mkdir()
        self.install_worker(other)
        self.hold_lock()
        self.assert_rebuilt(self.setup())

    def test_runs_without_an_installed_worker(self):
        self.hold_lock()
        self.assert_rebuilt(self.setup())

    def test_refuses_when_the_worker_configuration_cannot_be_read(self):
        self.install_worker(self.checkout)
        self.config.write_text('{"state_dir": ')
        result = self.setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not tell whether the News worker is running", result.stderr)
        self.assertNotIn("state_dir", result.stderr)
        self.assertTrue(self.marker.exists())

    def test_guard_probes_the_lock_the_worker_takes(self):
        from news.setup_guard import worker_lock

        with patch.dict(os.environ, {"HOME": str(self.home)}):
            for settings in ({}, {"state_dir": "~/custom-state"}):
                with self.subTest(settings=settings):
                    with self.hold_lock(worker_lock(settings)) as lock:
                        output = io.StringIO()
                        with contextlib.redirect_stdout(output):
                            self.assertEqual(run(dict(settings, claude="/mock/claude")), 0)
                        self.assertIn("already running; this start was skipped", output.getvalue())
                        fcntl.flock(lock, fcntl.LOCK_UN)


if __name__ == "__main__":
    unittest.main()
