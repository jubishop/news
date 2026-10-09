"""Verify the application checks that bin/check --full runs, with simulated tools."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
COMMANDS = (
    ["python", "-B", "-c", "import news"],
    ["python", "-B", "-m", "unittest", "discover", "-s", "tests/app", "-v"],
    ["python", "-B", "tests/test_browser.py"],
    ["shellcheck", "--shell=sh", "ops/install-server", "ops/deploy-main", "ops/install-worker", "bin/worker"],
)
RECORDER = (
    "import json, os, sys\n"
    "command = [os.path.basename(sys.argv[0]), *sys.argv[1:]]\n"
    "with open(os.environ['CHECK_EVENTS'], 'a') as stream:\n"
    "    stream.write(json.dumps({'command': command, 'cwd': os.getcwd()}) + '\\n')\n"
    "if command == json.loads(os.environ.get('FAIL_COMMAND', 'null')):\n"
    "    print('application check failed: ' + ' '.join(command), file=sys.stderr)\n"
    "    sys.exit(17)\n"
)


class CheckApplicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="news application checks ")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.repo = self.base / "checkout"
        (self.repo / "bin").mkdir(parents=True)
        shutil.copy2(ROOT / "bin/check-application", self.repo / "bin/check-application")
        self.events = self.base / "events.jsonl"
        tools = self.base / "tools"
        self.tool(self.repo / ".venv/bin/python")
        self.tool(tools / "shellcheck")
        self.env = {key: value for key, value in os.environ.items() if key != "FAIL_COMMAND"}
        self.env.update(PATH=os.pathsep.join((str(tools), "/usr/bin", "/bin")), CHECK_EVENTS=str(self.events))

    def tool(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!" + sys.executable + "\n" + RECORDER)
        path.chmod(0o755)

    def check(self, **extra):
        # Start outside the checkout to prove the script runs from its own root.
        return subprocess.run([str(self.repo / "bin/check-application")], cwd=self.base,
                              env=self.env | extra, text=True, capture_output=True, timeout=60)

    def recorded(self):
        if not self.events.exists():
            return []
        return [json.loads(line) for line in self.events.read_text().splitlines()]

    def test_runs_import_application_browser_and_shell_checks_in_order_from_the_root(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.recorded()
        self.assertEqual([event["command"] for event in events], list(COMMANDS))
        self.assertEqual({event["cwd"] for event in events}, {str(self.repo)})

    def test_a_failure_propagates_and_stops_later_checks(self):
        for index, command in enumerate(COMMANDS):
            with self.subTest(command=command):
                self.events.unlink(missing_ok=True)
                result = self.check(FAIL_COMMAND=json.dumps(command))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("application check failed: " + " ".join(command), result.stderr)
                self.assertEqual([event["command"] for event in self.recorded()], list(COMMANDS[:index + 1]))


if __name__ == "__main__":
    unittest.main()
