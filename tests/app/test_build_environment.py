"""Build a release environment with the deploy kit's script, with host commands faked."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from host_tools import install_host_tools


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/build-environment"
# A fake interpreter: `-m venv` makes a minimal environment, and `-m pip`
# records the install and can leave behind files that root must not adopt.
FAKE_PYTHON = r"""#!/bin/sh
printf '%s|%s|%s\n' "$0" "$*" "$PWD" >> "$TEST_LOG"
case "$1 $2" in
    '-m venv')
        mkdir -p "$3/bin" "$3/lib"
        ln -s "$0" "$3/bin/python"
        ;;
    '-m pip')
        [ "$TEST_FAIL" != pip ] || exit 1
        environment=${0%/bin/python}
        printf 'package\n' > "$environment/lib/package.py"
        case "$TEST_LEAVE" in
            hardlink) ln "$environment/lib/package.py" "$environment/lib/other.py" ;;
            fifo) mkfifo "$environment/lib/pipe" ;;
        esac
        ;;
esac
"""


class BuildEnvironmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.release = self.base / "opt/news/releases/fixture"
        self.release.mkdir(parents=True)
        self.requirements = self.release / "requirements.txt"
        self.requirements.touch()
        self.environment = self.release / ".venv"
        self.log = self.base / "log"
        tools = self.base / "bin"
        tools.mkdir()
        install_host_tools(tools)
        self.python = self.base / "python/bin/python3"
        self.python.parent.mkdir(parents=True)
        self.python.write_text(FAKE_PYTHON)
        self.python.chmod(0o755)
        self.env = os.environ | {"PATH": f"{tools}{os.pathsep}{os.environ['PATH']}", "TEST_LOG": str(self.log)}

    def build(self, environment=None, **extra):
        self.log.unlink(missing_ok=True)
        target = self.environment if environment is None else environment
        result = subprocess.run(
            ["sh", str(SCRIPT), str(self.python), str(target), str(self.requirements)],
            env=self.env | extra, capture_output=True, text=True,
        )
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return result, [call.split("|") for call in calls]

    def test_builds_as_news_in_a_sandbox_and_then_takes_ownership(self):
        result, calls = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        names = [call[0].rsplit("/", 1)[-1] for call in calls]
        self.assertEqual(names, ["id", "install", "systemd-run", "python3", "python", "chown"])
        unit = calls[2][1].split()
        for option in (
            "--wait", "--collect", "--pipe", "--property=User=news", "--property=Group=news",
            "--property=NoNewPrivileges=yes", "--property=ProtectSystem=strict",
            f"--property=ReadWritePaths={self.environment}",
        ):
            self.assertIn(option, unit)
        self.assertEqual(calls[3][1], f"-m venv {self.environment}")
        self.assertEqual(calls[4][1], f"-m pip install --no-cache-dir --disable-pip-version-check "
                                      f"--require-hashes -r {self.requirements}")
        self.assertEqual(calls[5][1], f"-R root:root {self.environment}")
        self.assertTrue((self.environment / "lib/package.py").is_file())

    def test_failed_build_removes_the_environment(self):
        for failure in ("unit", "pip"):
            with self.subTest(failure):
                result, calls = self.build(TEST_FAIL=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.environment.exists())
                self.assertNotIn("chown", [call[0] for call in calls])

    def test_refuses_to_adopt_links_to_other_files_or_special_files(self):
        for leftover in ("hardlink", "fifo"):
            with self.subTest(leftover):
                result, calls = self.build(TEST_LEAVE=leftover)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unexpected files", result.stderr)
                self.assertFalse(self.environment.exists())
                self.assertNotIn("chown", [call[0] for call in calls])

    def test_invalid_requests_change_nothing(self):
        self.environment.mkdir()
        (self.environment / "kept").touch()
        for name, environment, extra in (
            ("existing environment", self.environment, {}),
            ("not root", self.release / ".venv-3.15.0", {"TEST_UID": "1000"}),
            ("relative path", Path(".venv-3.15.0"), {}),
            ("not an environment", self.release / "news", {}),
        ):
            with self.subTest(name):
                result, calls = self.build(environment, **extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse([call for call in calls if call[0] != "id"])
                self.assertTrue((self.environment / "kept").exists())
                self.assertEqual(sorted(path.name for path in self.release.iterdir()),
                                 [".venv", "requirements.txt"])


if __name__ == "__main__":
    unittest.main()
