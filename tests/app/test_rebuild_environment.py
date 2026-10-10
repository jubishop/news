"""Rebuild the active release's environment, with interpreters and runuser faked."""

import contextlib
import fcntl
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/rebuild-environment"
SHARED_PYTHON = "#!/opt/python/current/bin/python3\n"
# A fake CPython: it answers the version probe, creates a minimal venv whose
# python links back to it, and records pip and import checks.
FAKE_PYTHON = r"""#!/bin/sh
printf '%s|%s|%s\n' "$0" "$*" "$PWD" >> "$TEST_LOG"
case "$1 $2" in
    '-m venv')
        [ "$TEST_FAIL" != venv ] || exit 1
        mkdir -p "$3/bin"
        ln -s "$0" "$3/bin/python"
        printf 'home = %s\nversion = @VERSION@\n' "${0%/*}" > "$3/pyvenv.cfg"
        ;;
    '-m pip') [ "$TEST_FAIL" != pip ] || exit 1 ;;
    '-B -c') [ "$TEST_FAIL" != import ] || exit 1 ;;
    *) exec "$TEST_PYTHON" -c "import sys; sys.version_info = (@TUPLE@); exec(sys.argv[1])" "$2" ;;
esac
"""
RUNUSER = r"""#!/bin/sh
printf 'runuser|%s|%s\n' "$*" "$PWD" >> "$TEST_LOG"
[ "$1 $2 $3" = '-u news --' ] || exit 64
shift 3
exec "$@"
"""


def load_command():
    loader = importlib.machinery.SourceFileLoader("rebuild_environment", str(SCRIPT))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


class RebuildEnvironmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.news = self.base / "opt/news"
        self.release = self.news / "releases" / ("a" * 40 + "-fixture")
        self.release.mkdir(parents=True)
        (self.release / "requirements.txt").touch()
        (self.news / "current").symlink_to(self.release)
        self.log = self.base / "log"
        tools = self.base / "bin"
        tools.mkdir()
        (tools / "runuser").write_text(RUNUSER)
        (tools / "runuser").chmod(0o755)
        self.environment = {
            "PATH": str(tools) + os.pathsep + os.environ["PATH"],
            "TEST_LOG": str(self.log),
            "TEST_PYTHON": sys.executable,
            "TEST_FAIL": "",
        }
        self.command = load_command()

    def interpreter(self, version, location="versions"):
        path = self.base / location / ("cpython-" + version) / "bin/python3"
        if not path.exists():
            path.parent.mkdir(parents=True)
            source = FAKE_PYTHON.replace("@VERSION@", version)
            path.write_text(source.replace("@TUPLE@", version.replace(".", ", ")))
            path.chmod(0o755)
        return path

    def legacy_environment(self, version):
        """Create the real .venv directory that install-server leaves in a release."""
        self.run_fake(self.interpreter(version), "-m", "venv", str(self.release / ".venv"))
        (self.release / ".venv/legacy").touch()

    def run_fake(self, *args):
        subprocess.run([str(arg) for arg in args], env=os.environ | self.environment, check=True)

    def rebuild(self, *args, failure="", uid=0):
        self.log.unlink(missing_ok=True)
        output = io.StringIO()
        with (
            patch.object(self.command, "NEWS", self.news),
            patch.object(self.command, "LOCK", self.base / "deploy.lock"),
            patch.object(self.command, "LOCK_WAIT", 0),
            patch("os.geteuid", return_value=uid),
            patch.dict(os.environ, self.environment | {"TEST_FAIL": failure}),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            code = self.command.main([str(arg) for arg in args])
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return code, calls, output.getvalue()

    def environments(self):
        return sorted(path.name for path in self.release.iterdir() if path.name.startswith(".venv"))

    def active(self):
        return os.readlink(self.release / ".venv")

    def test_first_rebuild_swaps_real_environment_for_link_and_keeps_it_for_rollback(self):
        self.legacy_environment("3.14.8")
        code, calls, output = self.rebuild(self.interpreter("3.15.0"))
        self.assertEqual(code, 0, output)
        self.assertEqual(self.active(), ".venv-3.15.0")
        self.assertEqual(self.environments(), [".venv", ".venv-3.14.8", ".venv-3.15.0"])
        self.assertTrue((self.release / ".venv-3.14.8/legacy").exists())
        environment = self.release / ".venv-3.15.0"
        requirements = self.release / "requirements.txt"
        self.assertIn(f"{environment}/bin/python|-m pip install --require-hashes -r {requirements}|", "\n".join(calls))
        verify = calls.index(f"runuser|-u news -- {environment}/bin/python -B -c import news|{self.release}")
        self.assertEqual(calls[verify + 1], f"{environment}/bin/python|-B -c import news|{self.release}")

    def test_rollback_reuses_the_environment_for_the_previous_interpreter(self):
        self.legacy_environment("3.14.8")
        self.assertEqual(self.rebuild(self.interpreter("3.15.0"))[0], 0)
        code, calls, output = self.rebuild(self.interpreter("3.14.8"))
        self.assertEqual(code, 0, output)
        self.assertEqual(self.active(), ".venv-3.14.8")
        self.assertTrue((self.release / ".venv-3.14.8/legacy").exists())
        self.assertFalse([call for call in calls if "-m venv" in call or "-m pip" in call])
        self.assertIn(f"{self.release}/.venv-3.14.8/bin/python|-B -c import news|{self.release}", calls)
        code, calls, output = self.rebuild(self.interpreter("3.15.0"))
        self.assertEqual(code, 0, output)
        self.assertEqual(self.active(), ".venv-3.15.0")
        self.assertFalse([call for call in calls if "-m pip" in call])

    def test_same_version_rebuild_replaces_the_real_environment(self):
        self.legacy_environment("3.14.8")
        code, calls, output = self.rebuild(self.interpreter("3.14.8", "shared"))
        self.assertEqual(code, 0, output)
        self.assertEqual(self.active(), ".venv-3.14.8")
        self.assertEqual(self.environments(), [".venv", ".venv-3.14.8"])
        self.assertFalse((self.release / ".venv-3.14.8/legacy").exists())
        self.assertIn("-m pip install", "\n".join(calls))

    def test_any_failure_leaves_the_active_environment_unchanged(self):
        for start in ("directory", "link"):
            for failure in ("venv", "pip", "import"):
                with self.subTest(start=start, failure=failure):
                    self.setUp()
                    self.legacy_environment("3.14.8")
                    if start == "link":
                        self.assertEqual(self.rebuild(self.interpreter("3.15.0"))[0], 0)
                    before = self.environments()
                    code, _, output = self.rebuild(self.interpreter("3.16.0"), failure=failure)
                    self.assertNotEqual(code, 0, output)
                    self.assertEqual(self.environments(), before)
                    if start == "link":
                        self.assertEqual(self.active(), ".venv-3.15.0")
                    else:
                        self.assertTrue((self.release / ".venv/legacy").exists())

    def test_python_older_than_314_is_rejected_before_building(self):
        self.legacy_environment("3.14.8")
        code, calls, output = self.rebuild(self.interpreter("3.13.9"))
        self.assertNotEqual(code, 0)
        self.assertIn("News requires Python 3.14 or later", output)
        self.assertFalse([call for call in calls if "-m venv" in call])
        self.assertEqual(self.environments(), [".venv"])

    def test_newer_major_python_is_accepted(self):
        self.legacy_environment("3.14.8")
        code, _, output = self.rebuild(self.interpreter("4.0.0"))
        self.assertEqual(code, 0, output)
        self.assertEqual(self.active(), ".venv-4.0.0")

    def test_environment_from_another_interpreter_is_rebuilt_only_when_inactive(self):
        self.legacy_environment("3.14.8")
        self.assertEqual(self.rebuild(self.interpreter("3.15.0"))[0], 0)
        other = self.interpreter("3.15.0", "elsewhere")
        code, _, output = self.rebuild(other)
        self.assertNotEqual(code, 0)
        self.assertIn("leaving it unchanged", output)
        self.assertEqual(self.active(), ".venv-3.15.0")
        self.assertEqual(self.rebuild(self.interpreter("3.14.8"))[0], 0)
        code, calls, output = self.rebuild(other)
        self.assertEqual(code, 0, output)
        self.assertEqual(self.active(), ".venv-3.15.0")
        self.assertEqual(os.path.realpath(self.release / ".venv/bin/python"), str(other))
        self.assertIn("-m pip install", "\n".join(calls))

    def test_busy_deployment_lock_changes_nothing(self):
        self.legacy_environment("3.14.8")
        with open(self.base / "deploy.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            code, calls, output = self.rebuild(self.interpreter("3.15.0"))
        self.assertNotEqual(code, 0)
        self.assertIn("deployment", output)
        self.assertFalse(calls)
        self.assertEqual(self.environments(), [".venv"])

    def test_invalid_invocations_change_nothing(self):
        self.legacy_environment("3.14.8")
        outside = self.base / "outside"
        outside.mkdir()
        python = self.interpreter("3.15.0")
        for name, args, uid in (
            ("not root", [python], 1000),
            ("no interpreter", [], 0),
            ("two interpreters", [python, python], 0),
            ("relative interpreter", ["python3"], 0),
            ("release outside releases", [python], 0),
        ):
            with self.subTest(name):
                if name == "release outside releases":
                    (self.news / "current").unlink()
                    (self.news / "current").symlink_to(outside)
                code, _, _ = self.rebuild(*args, uid=uid)
                self.assertNotEqual(code, 0)
                self.assertEqual(self.environments(), [".venv"])

    def test_host_entry_points_use_the_shared_python(self):
        for name in ("receive-release", "rebuild-environment"):
            with self.subTest(name):
                path = ROOT / "ops" / name
                self.assertEqual(path.read_text().splitlines(keepends=True)[0], SHARED_PYTHON)
                self.assertTrue(os.access(path, os.X_OK))


if __name__ == "__main__":
    unittest.main()
