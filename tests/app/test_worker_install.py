"""LaunchAgent generation, the launchd and crontab boundaries, and migration from cron."""

import fcntl
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from news.worker_install import LABEL, install

LEGACY = "0 6 * * * cd /old/news && /old/news/.venv/bin/python -B -m news.worker > /old/cron.log 2>&1 # news-reporting-worker\n"


class LaunchAgentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="news launchd ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root / "worker.json"
        self.config.write_text(json.dumps({"state_dir": str(self.root / "state"), "claude": "/mock/claude"}))
        self.config.chmod(0o600)
        (self.root / ".venv/bin").mkdir(parents=True)
        (self.root / ".venv/bin/python").touch()
        self.agent = self.root / "home/Library/LaunchAgents" / f"{LABEL}.plist"
        self.enterContext(patch.dict(os.environ, {"HOME": str(self.root / "home")}))
        self.crontab = "MAILTO=owner@example.com\n17 3 * * * /existing/backup\n" + LEGACY
        self.loaded = None
        self.stuck = False
        self.calls = []
        self.enterContext(patch("news.worker_install.subprocess.run", side_effect=self.command))
        self.readlink = os.readlink
        self.enterContext(patch("os.readlink", side_effect=lambda path, *args, **kwargs: "/var/db/timezone/zoneinfo/America/Los_Angeles" if str(path) == "/etc/localtime" else self.readlink(path, *args, **kwargs)))

    def command(self, args, **kwargs):
        self.calls.append(args)
        if args == ["crontab", "-l"]:
            if self.crontab is None:
                return subprocess.CompletedProcess(args, 1, "", "crontab: no crontab for owner\n")
            return subprocess.CompletedProcess(args, 0, self.crontab, "")
        if args == ["crontab", "-"]:
            self.crontab = kwargs["input"]
        if args == ["crontab", "-r"]:
            self.crontab = None
        if args[:2] == ["launchctl", "bootstrap"]:
            self.assertEqual(args[2], f"gui/{os.getuid()}")
            self.loaded = plistlib.loads(Path(args[3]).read_bytes())
        if args[:2] == ["launchctl", "bootout"]:
            if self.stuck:
                return subprocess.CompletedProcess(args, 5, "", "Boot-out failed: 5: Input/output error")
            was_loaded, self.loaded = self.loaded is not None, None
            return subprocess.CompletedProcess(args, 0 if was_loaded else 3, "", "")
        if args[:2] == ["launchctl", "print"]:
            return subprocess.CompletedProcess(args, 0 if self.loaded else 113, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    def changes(self):
        return [args[:2] for args in self.calls if args[:2] in (["crontab", "-"], ["crontab", "-r"], ["launchctl", "bootstrap"], ["launchctl", "bootout"])]

    def test_preview_describes_the_daily_agent_without_installing(self):
        job = plistlib.loads(install(self.config, self.root).encode())
        self.assertEqual(job["Label"], LABEL)
        self.assertEqual(job["StartCalendarInterval"], {"Hour": 6, "Minute": 0})
        self.assertEqual(job["WorkingDirectory"], str(self.root.resolve()))
        command = job["ProgramArguments"][-1]
        self.assertEqual(job["ProgramArguments"][:2], ["/bin/sh", "-c"])
        self.assertIn("-m news.worker --config '" + str(self.config.resolve()) + "'", command)
        self.assertIn("'" + str((self.root / "state/scheduled.log").resolve()) + "'", command)
        self.assertFalse(self.agent.exists())
        self.assertEqual(self.changes(), [])

    def test_install_loads_the_agent_and_removes_only_the_legacy_cron_entry(self):
        install(self.config, self.root, apply=True)
        self.assertEqual(self.loaded, plistlib.loads(self.agent.read_bytes()))
        self.assertEqual(self.loaded["Label"], LABEL)
        self.assertEqual(self.crontab, "MAILTO=owner@example.com\n17 3 * * * /existing/backup\n")
        self.assertIn([str(self.root.resolve() / ".venv/bin/python"), "-B", "-m", "news.worker", "--config", str(self.config.resolve()), "--check"], self.calls)

    def test_repeated_install_is_a_no_op_and_a_changed_agent_is_reloaded(self):
        install(self.config, self.root, apply=True)
        installed, self.calls = self.agent.read_bytes(), []
        install(self.config, self.root, apply=True)
        self.assertEqual(self.changes(), [])
        self.assertEqual(self.agent.read_bytes(), installed)
        self.agent.write_bytes(installed.replace(b"<integer>6</integer>", b"<integer>1</integer>"))
        install(self.config, self.root, apply=True)
        self.assertEqual(self.changes(), [["launchctl", "bootout"], ["launchctl", "bootstrap"]])
        self.assertEqual(self.agent.read_bytes(), installed)
        self.assertEqual(self.loaded["StartCalendarInterval"], {"Hour": 6, "Minute": 0})

    def test_crontab_holding_only_the_legacy_entry_is_removed(self):
        self.crontab = LEGACY
        install(self.config, self.root, apply=True)
        self.assertIsNone(self.crontab)
        self.assertEqual(self.changes(), [["crontab", "-r"], ["launchctl", "bootstrap"]])

    def test_failed_unload_keeps_the_old_agent_and_a_later_install_reloads(self):
        install(self.config, self.root, apply=True)
        installed = self.agent.read_bytes()
        old = installed.replace(b"<integer>6</integer>", b"<integer>1</integer>")
        self.agent.write_bytes(old)
        self.loaded = plistlib.loads(old)
        self.stuck = True
        with self.assertRaisesRegex(Exception, "unload"):
            install(self.config, self.root, apply=True)
        self.assertEqual(self.agent.read_bytes(), old)
        self.assertEqual(self.loaded["StartCalendarInterval"], {"Hour": 1, "Minute": 0})
        self.stuck = False
        install(self.config, self.root, apply=True)
        self.assertEqual(self.agent.read_bytes(), installed)
        self.assertEqual(self.loaded["StartCalendarInterval"], {"Hour": 6, "Minute": 0})

    def test_install_without_any_crontab_leaves_crontab_alone(self):
        self.crontab = None
        install(self.config, self.root, apply=True)
        self.assertIsNone(self.crontab)
        self.assertEqual(self.changes(), [["launchctl", "bootstrap"]])

    def test_running_worker_is_never_interrupted(self):
        (self.root / "state").mkdir(mode=0o700)
        with (self.root / "state/worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaisesRegex(Exception, "running"):
                install(self.config, self.root, apply=True)
        self.assertEqual(self.changes(), [])
        self.assertFalse(self.agent.exists())

    def test_wrong_system_timezone_is_rejected_before_install(self):
        with patch("os.readlink", side_effect=lambda path, *args, **kwargs: "/usr/share/zoneinfo/UTC" if str(path) == "/etc/localtime" else self.readlink(path, *args, **kwargs)):
            with self.assertRaisesRegex(Exception, "Pacific"):
                install(self.config, self.root, apply=True)
        self.assertEqual(self.changes(), [])

    def test_crontab_read_error_changes_nothing(self):
        def unreadable(args, **kwargs):
            if args == ["crontab", "-l"]:
                self.calls.append(args)
                return subprocess.CompletedProcess(args, 1, "", "permission denied")
            return self.command(args, **kwargs)
        with patch("news.worker_install.subprocess.run", side_effect=unreadable):
            with self.assertRaisesRegex(Exception, "crontab"):
                install(self.config, self.root, apply=True)
        self.assertEqual(self.changes(), [])
        self.assertFalse(self.agent.exists())
