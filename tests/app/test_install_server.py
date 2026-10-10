"""Run the real installer in a disposable Linux root, never against host paths."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform == "linux", "Installer integration requires Linux chroot")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.prefix = [] if os.geteuid() == 0 else ["sudo", "-n"]
        for executable in ("sh", "mkdir", "ln", "mv", "cat"):
            source = Path(shutil.which(executable)).resolve()
            dependencies = subprocess.check_output(["ldd", str(source)], text=True)
            for library in re.findall(r"(/[^\s()]+)", dependencies):
                self.copy(Path(library), library)
            self.copy(source, "/bin/" + executable)
        for directory in (
            "etc/news", "etc/systemd/system", "run/lock", "dev",
            "opt/news/releases/fixture/news", "opt/news/releases/fixture/ops/systemd",
            "opt/news/releases/fixture/.venv/bin", "var/lib/news", "var/lib/news-backup",
        ):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        (self.root / "dev/null").touch()
        for filename in ("app.env", "backup.env"):
            (self.root / "etc/news" / filename).touch()
        for filename in ("news/schema.sql", "requirements.txt"):
            (self.root / "opt/news/releases/fixture" / filename).touch()
        self.units = [
            "news.service", "news-maintain.service", "news-backup.service",
            "news-restore-check.service", "news-maintain.timer", "news-backup.timer",
            "news-restore-check.timer",
        ]
        for unit in self.units:
            (self.root / "etc/systemd/system" / unit).touch()
            (self.root / "opt/news/releases/fixture/ops/systemd" / unit).touch()
        shim = self.root / "bin/boundary"
        shim.write_text('''#!/bin/sh
name=${0##*/}
printf '%s\\n' "$name $*" >> /events
case "$name" in
  id) printf '0\\n' ;;
  realpath) printf '%s\\n' "$1" ;;
  readlink) printf '/opt/news/releases/previous\\n' ;;
  systemctl)
    if [ -f /fail-stop ] && [ "$1 $2" = 'stop news-maintain.timer' ]; then exit 1; fi
    if [ -f /fail-maintain ] && [ "$1 $2" = 'start news-maintain.service' ]; then exit 1; fi
    ;;
  systemd-run) [ ! -f /fail-migrate ] || exit 1 ;;
  curl) [ ! -f /fail-health ] || exit 1 ;;
  flock) [ ! -f /fail-lock ] || exit 1 ;;
  python)
    if [ "$1" = - ]; then cat > /snapshot-program; printf 'saved' > /var/lib/news-backup/pre-release.sqlite3; fi
    ;;
esac
exit 0
''')
        shim.chmod(0o755)
        for name in (
            "id", "realpath", "readlink", "systemctl", "systemd-run", "curl",
            "flock", "restic", "install", "useradd", "chown", "chmod",
        ):
            (self.root / "bin" / name).symlink_to("boundary")
        # Only the shared runtime exists; the retired dedicated interpreter is absent.
        (self.root / "opt/python/current/bin").mkdir(parents=True)
        (self.root / "opt/python/current/bin/python3").symlink_to("/bin/boundary")
        (self.root / "opt/news/releases/fixture/.venv/bin/python").symlink_to("/bin/boundary")
        installer = Path(os.environ.get("TEST_INSTALLER_SOURCE", ROOT / "ops/install-server"))
        self.copy(installer, "/installer")

    def copy(self, source, destination):
        target = self.root / destination.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def install(self, failure=None):
        if failure:
            (self.root / ("fail-" + failure)).touch()
        # Keep the fixture log readable by the test runner after root writes it.
        events_path = self.root / "events"
        events_path.touch(mode=0o600)
        result = subprocess.run(
            self.prefix + ["chroot", str(self.root), "/bin/sh", "/installer", "/opt/news/releases/fixture"],
            env=os.environ | {"PATH": "/bin:/usr/bin:/usr/sbin:/sbin"},
            capture_output=True, text=True,
        )
        events = events_path.read_text()
        return result, events

    def test_missing_configuration_fails_before_changing_services(self):
        (self.root / "etc/news/backup.env").unlink()
        result, events = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing /etc/news/backup.env", result.stderr)
        self.assertNotIn("systemctl", events)

    def test_backup_migrate_health_maintenance_and_timers_in_order(self):
        (self.root / "var/lib/news/news.sqlite3").write_text("existing data")
        (self.root / "var/lib/news-backup/pre-release.sqlite3").touch(mode=0o600)
        result, events = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "var/lib/news-backup/pre-release.sqlite3").read_text(), "saved")
        positions = [events.index(event) for event in (
            "python3 -m venv /opt/news/releases/fixture/.venv\n",
            "systemctl stop news.service", "python -\n",
            "install -m 0755 /opt/news/releases/fixture/ops/rebuild-environment "
            "/usr/local/sbin/news-rebuild-environment\n",
            "systemd-run --wait",
            "systemctl enable --now news.service", "curl --fail",
            "systemctl start news-maintain.service", "systemctl enable --now news-maintain.timer",
        )]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(os.readlink(self.root / "opt/news/current"), "/opt/news/releases/fixture")

    def test_cannot_stop_writer_means_no_migration(self):
        result, events = self.install("stop")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("systemd-run", events)
        self.assertNotIn("systemctl enable", events)

    def test_migration_failure_keeps_services_stopped(self):
        result, events = self.install("migrate")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("systemctl enable", events)
        self.assertIn("News remains stopped", result.stderr)

    def test_health_or_maintenance_failure_stops_web_and_timers(self):
        for failure in ("health", "maintain"):
            with self.subTest(failure=failure):
                result, events = self.install(failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("systemctl enable --now news-maintain.timer", events)
                self.assertIn("systemctl stop news-maintain.timer news-backup.timer", events)
                (self.root / ("fail-" + failure)).unlink()
                (self.root / "events").unlink()

    def test_lock_failure_leaves_running_release_alone(self):
        result, events = self.install("lock")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("systemctl", events)
        self.assertNotIn("python", events)


if __name__ == "__main__":
    unittest.main()
