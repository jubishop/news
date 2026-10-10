"""Application runtime rejection and checkout-local environment replacement."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from news.worker_claude import preflight
from news.worker_io import WorkerError


ROOT = Path(__file__).resolve().parents[2]
PROGRAMS = [
    "import news",
    "import runpy; sys.argv = ['reporters.py', '--help']; "
    "runpy.run_path('.agents/skills/news-reporters/scripts/reporters.py', run_name='__main__')",
]


class RuntimeTests(unittest.TestCase):
    def run_as(self, version, program):
        return subprocess.run(
            [sys.executable, "-c", f"import flask; import sys; sys.version_info = {version!r}; " + program],
            cwd=ROOT, capture_output=True, text=True,
        )

    def test_application_and_reporter_helper_reject_python_313(self):
        for program in PROGRAMS:
            with self.subTest(program=program):
                result = self.run_as((3, 13, 0, "final", 0), program)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("requires Python 3.14 or later", result.stderr)

    def test_application_and_reporter_helper_accept_newer_python(self):
        for version in ((3, 15, 0, "final", 0), (4, 0, 0, "final", 0)):
            for program in PROGRAMS:
                with self.subTest(version=version, program=program):
                    result = self.run_as(version, program)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_claude_code_gate_rejects_only_releases_below_its_minimum(self):
        with tempfile.TemporaryDirectory() as directory:
            claude = Path(directory) / "claude"
            claude.write_text(f"#!{sys.executable}\n" + """
import json, pathlib, sys
if "--version" in sys.argv:
    print(pathlib.Path(__file__).with_name("version").read_text() + " (Claude Code)")
else:
    print(json.dumps({"loggedIn": True, "authMethod": "claude.ai"}))
""")
            claude.chmod(0o700)
            for version, accepted in (("2.1.295", False), ("2.1.296", True), ("3.0.0", True), ("4.2.0", True)):
                with self.subTest(version=version):
                    claude.with_name("version").write_text(version)
                    if accepted:
                        preflight({"claude": str(claude)})
                    else:
                        with self.assertRaisesRegex(WorkerError, "Claude Code 2.1.296 or later"):
                            preflight({"claude": str(claude)})

    def test_setup_replaces_old_environment_only_after_runtime_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            shutil.copy2(ROOT / "bin/app-setup", root / "bin/app-setup")
            marker = root / ".venv/old-runtime"
            # The default interpreter is python3; its runtime check sees the simulated version.
            shim = root / "bin/python3"
            shim.write_text(f'''#!/bin/sh
set -eu
if [ "$1" = -c ]; then
    exec "{sys.executable}" -c "import sys; sys.version_info = tuple(map(int, sys.argv.pop(1).split('.'))); exec(sys.argv[1])" "$TEST_VERSION" "$2"
elif [ "$1 $2" = '-m venv' ]; then
    if [ "$3" = --clear ]; then rm -rf .venv; fi
    mkdir -p .venv/bin
    cp "$0" .venv/bin/python
fi
''')
            shim.chmod(0o755)
            env = dict(os.environ, PATH=os.pathsep.join([str(root / "bin"), "/usr/bin", "/bin"]))
            env.pop("NEWS_PYTHON", None)
            for version, accepted in (("3.13.9", False), ("3.14.0", True), ("3.15.0", True), ("4.0.0", True)):
                with self.subTest(version=version):
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.touch()
                    result = subprocess.run(["sh", str(root / "bin/app-setup")],
                                            env=env | {"TEST_VERSION": version}, capture_output=True, text=True)
                    if accepted:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertFalse(marker.exists())
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("News requires Python 3.14 or later", result.stderr)
                        self.assertTrue(marker.exists())
