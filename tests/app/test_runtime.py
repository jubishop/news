"""Application runtime rejection and checkout-local environment replacement."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class RuntimeTests(unittest.TestCase):
    def test_application_and_reporter_helper_reject_python_313(self):
        programs = [
            "import news",
            "import runpy; sys.argv = ['reporters.py', '--help']; "
            "runpy.run_path('.agents/skills/news-reporters/scripts/reporters.py', run_name='__main__')",
        ]
        for program in programs:
            with self.subTest(program=program):
                result = subprocess.run(
                    [sys.executable, "-c", "import flask; import sys; sys.version_info = (3, 13, 0, 'final', 0); " + program],
                    cwd=ROOT, capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("requires Python 3.14", result.stderr)

    def test_setup_replaces_old_environment_only_after_runtime_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            shutil.copy2(ROOT / "bin/app-setup", root / "bin/app-setup")
            (root / ".venv/bin").mkdir(parents=True)
            marker = root / ".venv/old-runtime"
            marker.touch()
            shim = root / "bin/python3.14"
            shim.write_text('''#!/bin/sh
set -eu
case "$0" in *python3.12) echo 'Wrong default interpreter' >&2; exit 42 ;; esac
if [ "$1" = -c ]; then
    [ "${REJECT_RUNTIME:-0}" = 0 ] || exit 1
elif [ "$1 $2" = '-m venv' ]; then
    if [ "$3" = --clear ]; then rm -rf .venv; fi
    mkdir -p .venv/bin
    cp "$0" .venv/bin/python
fi
''')
            shim.chmod(0o755)
            (root / "bin/python3.12").symlink_to("python3.14")
            env = dict(os.environ, PATH=str(root / "bin") + os.pathsep + os.environ["PATH"])
            env.pop("NEWS_PYTHON", None)
            rejected = subprocess.run(["sh", str(root / "bin/app-setup")],
                                      env=env | {"REJECT_RUNTIME": "1"}, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertTrue(marker.exists())
            accepted = subprocess.run(["sh", str(root / "bin/app-setup")],
                                      env=env, capture_output=True, text=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertFalse(marker.exists())
