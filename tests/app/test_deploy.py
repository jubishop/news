"""Release entry points, with SSH and systemd replaced at their boundaries."""

import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


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


class ReceiveReleaseTests(unittest.TestCase):
    def test_unsupported_python_stops_before_accepting_a_release(self):
        with patch("sys.version_info", (3, 13, 0)):
            code, calls, _ = self.receive(self.archive())
        self.assertNotEqual(code, 0)
        self.assertFalse(calls)

    def test_newer_python_accepts_a_release(self):
        for version in ((3, 15, 0), (4, 0, 0)):
            with self.subTest(version=version), patch("sys.version_info", version):
                code, calls, _ = self.receive(self.archive())
                self.assertEqual(code, 0)
                self.assertEqual(calls[0].args[0][0], "systemd-run")

    def archive(self, extra=None):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w") as archive:
            for name in ("ops/install-server", "news/schema.sql", "requirements.txt"):
                member = tarfile.TarInfo(name)
                member.size = 7
                archive.addfile(member, io.BytesIO(b"fixture"))
            if extra:
                archive.addfile(extra, io.BytesIO(b"x" * extra.size))
        return data.getvalue()

    def receive(self, data, command=None, result=0):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "release"
            release.mkdir()
            stdin = io.TextIOWrapper(io.BytesIO(data))
            with (
                patch.dict(os.environ, {"SSH_ORIGINAL_COMMAND": command or f"deploy {REVISION}"}),
                patch("sys.stdin", stdin),
                patch("os.geteuid", return_value=0),
                patch("tempfile.mkdtemp", return_value=str(release)),
                patch("subprocess.run") as run,
            ):
                run.return_value = subprocess.CompletedProcess([], result)
                try:
                    runpy.run_path(str(ROOT / "ops/receive-release"), run_name="__main__")
                    code = 0
                except SystemExit as error:
                    code = error.code
                files = {str(p.relative_to(release)): p.read_bytes() for p in release.rglob("*") if p.is_file()}
                return code, run.call_args_list, files

    def test_installs_uploaded_release_with_revision_and_durable_service(self):
        code, calls, files = self.receive(self.archive())
        self.assertEqual(code, 0)
        self.assertEqual(files["REVISION"], (REVISION + "\n").encode())
        self.assertEqual(calls[0].args[0][0], "systemd-run")
        self.assertIn("--wait", calls[0].args[0])
        self.assertNotIn("--pipe", calls[0].args[0])
        self.assertTrue(calls[0].args[0][-1].endswith("/release"))
        self.assertEqual(calls[1].args[0][0], "journalctl")

    def test_installer_failure_is_reported(self):
        code, _, _ = self.receive(self.archive(), result=1)
        self.assertEqual(code, 1)

    def test_rejects_arbitrary_ssh_commands(self):
        code, calls, _ = self.receive(self.archive(), command="sh -c id")
        self.assertNotEqual(code, 0)
        self.assertFalse(calls)

    def test_rejects_archive_paths_and_links_before_installing(self):
        for name, kind, target in (
            ("../escape", tarfile.REGTYPE, ""),
            ("/etc/escape", tarfile.REGTYPE, ""),
            (".env", tarfile.REGTYPE, ""),
            ("ops/link", tarfile.SYMTYPE, "/etc"),
            ("ops/hardlink", tarfile.LNKTYPE, "ops/install-server"),
        ):
            with self.subTest(name=name):
                member = tarfile.TarInfo(name)
                member.type, member.linkname = kind, target
                code, calls, _ = self.receive(self.archive(member))
                self.assertNotEqual(code, 0)
                self.assertFalse(calls)


if __name__ == "__main__":
    unittest.main()
