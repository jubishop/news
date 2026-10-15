"""The release client, with Git, SSH, and curl replaced at their boundaries.

tests/app/test_receive_release.py covers the host side of the deploy key.
"""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
REVISION = "a" * 40


class DeployClientTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / "calls"
        for name, body in {
            "git": 'if [ "$1" = ls-remote ]; then printf "%s\\trefs/heads/main\\n" "$REMOTE_REVISION"; else printf archive > "${3#--output=}"; fi',
            "ssh": 'cat > "$TEST_DIRECTORY/archive"; exit "${SSH_RESULT:-0}"',
            "curl": 'exit "${CURL_RESULT:-0}"',
        }.items():
            executable = self.directory / name
            executable.write_text(
                '#!/bin/sh\nprintf "%s\\n" "' + name + ' $*" >> "$TEST_LOG"\n' + body + "\n"
            )
            executable.chmod(0o755)
        self.environment = dict(
            os.environ,
            PATH=str(self.directory) + os.pathsep + os.environ["PATH"],
            TEST_DIRECTORY=str(self.directory),
            TEST_LOG=str(self.log),
            REMOTE_REVISION=REVISION,
            NEWS_DEPLOY_HOST="fixture.example",
            NEWS_DEPLOY_KEY=str(self.directory / "key"),
            NEWS_DEPLOY_KNOWN_HOSTS=str(self.directory / "known_hosts"),
        )

    def deploy(self, revision=REVISION, **environment):
        return subprocess.run(
            ["sh", str(ROOT / "ops/deploy-main"), revision],
            env=self.environment | environment,
            capture_output=True,
            text=True,
        )

    def test_uploads_exact_main_revision_and_checks_public_health(self):
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text()
        self.assertIn(f"archive --format=tar --output=", calls)
        self.assertIn(f"{REVISION} news ops requirements.txt", calls)
        self.assertIn(f"root@fixture.example deploy {REVISION}", calls)
        self.assertIn("StrictHostKeyChecking=yes", calls)
        self.assertIn("https://news.jubishop.com/health", calls)

    def test_old_revision_is_skipped_without_contacting_server(self):
        result = self.deploy(REMOTE_REVISION="b" * 40)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ssh ", self.log.read_text())
        self.assertIn("superseded", result.stdout)

    def test_server_failure_prevents_success_and_public_check(self):
        result = self.deploy(SSH_RESULT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("curl ", self.log.read_text())

    def test_public_health_failure_is_a_deployment_failure(self):
        self.assertNotEqual(self.deploy(CURL_RESULT="22").returncode, 0)

    def test_invalid_revision_never_reaches_external_commands(self):
        self.assertNotEqual(self.deploy("main; false").returncode, 0)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
