"""Exercise the deploy key's forced command against disposable host directories.

The receiver is the only command that the production deploy key can run as
root. These tests load it from ops/, point its host paths at a temporary
directory, install the checked deploy kit there, and replace systemd at its
command boundary.
"""

import contextlib
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
REVISION = "a" * 40
ACTIVE = "b" * 40


def load_receiver():
    loader = SourceFileLoader("receive_release", str(ROOT / "ops/receive-release"))
    spec = spec_from_loader(loader.name, loader)
    assert spec
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def checked_ops():
    """The ops/ files at this checkout, as `git archive REVISION ops/` names them."""
    return {
        str(path.relative_to(ROOT)): path.read_bytes()
        for path in sorted((ROOT / "ops").rglob("*"))
        if path.is_file()
    }


def member(name, content=b"", kind=tarfile.REGTYPE, mode=0o644, target=""):
    info = tarfile.TarInfo(name)
    info.type, info.mode, info.linkname = kind, mode, target
    if kind == tarfile.REGTYPE:
        info.size = len(content)
    return info, content


def release_members(ops=None):
    """The shape of `git archive REVISION news ops requirements.txt`."""
    members = [
        member("news/", kind=tarfile.DIRTYPE, mode=0o775),
        member("news/__init__.py", b"# news\n", mode=0o664),
        member("news/schema.sql", b"-- schema\n", mode=0o664),
        member("ops/", kind=tarfile.DIRTYPE, mode=0o775),
        member("ops/systemd/", kind=tarfile.DIRTYPE, mode=0o775),
        member("requirements.txt", b"flask==3 --hash=sha256:00\n", mode=0o664),
    ]
    files = checked_ops() if ops is None else ops
    return members + [member(name, data, mode=0o775) for name, data in files.items()]


def archive_bytes(members):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for info, content in members:
            archive.addfile(info, io.BytesIO(content) if info.isreg() else None)
    return buffer.getvalue()


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.receiver = load_receiver()
        self.news = self.base / "opt/news"
        (self.news / "releases" / ACTIVE).mkdir(parents=True)
        (self.news / "releases" / ACTIVE / "REVISION").write_text(ACTIVE + "\n")
        (self.news / "current").symlink_to(self.news / "releases" / ACTIVE)
        self.kit = self.base / "usr/local/lib/news-deploy"
        self.install_kit(checked_ops())
        for name, value in (("NEWS", self.news), ("KIT", self.kit)):
            patcher = patch.object(self.receiver, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.installer_result = 0

    def install_kit(self, ops):
        """Install the kit as bin/install-deploy-kit does: the receiver stays in ops/."""
        self.kit.mkdir(parents=True, exist_ok=True)
        for path in self.kit.iterdir():
            path.unlink()
        for name, data in self.receiver.kit_files(ops.items()).items():
            if name != "receive-release":
                (self.kit / name).write_bytes(data)

    def releases(self):
        return sorted(path.name for path in (self.news / "releases").iterdir())

    def receive(self, command, data=b"", uid=0):
        calls = []

        def run(args, **options):
            calls.append((list(args), options))
            return subprocess.CompletedProcess(args, self.installer_result if args[0] == "systemd-run" else 0)

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, {"SSH_ORIGINAL_COMMAND": command}),
            patch("sys.stdin", io.TextIOWrapper(io.BytesIO(data))),
            patch.object(self.receiver.os, "geteuid", return_value=uid),
            patch.object(self.receiver.subprocess, "run", side_effect=run),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = self.receiver.main()
        return code, calls, stdout.getvalue(), stderr.getvalue()

    def deploy(self, members=None):
        return self.receive(f"deploy {REVISION}", archive_bytes(release_members() if members is None else members))

    def test_status_reports_the_active_revision_and_installed_kit(self):
        code, calls, stdout, _ = self.receive("status")
        self.assertEqual(code, 0)
        self.assertFalse(calls)
        status = json.loads(stdout)
        self.assertEqual(status["active"], ACTIVE)
        expected = self.receiver.kit_digest(self.receiver.kit_files(checked_ops().items()))
        self.assertEqual(status["kit"], expected)
        (self.news / "current").unlink()
        self.assertIsNone(json.loads(self.receive("status")[2])["active"])

    def test_deploy_runs_the_installed_kit_and_never_the_release_scripts(self):
        code, calls, stdout, stderr = self.deploy()
        self.assertEqual(code, 0, stderr)
        self.assertIn("Deploying " + REVISION, stdout)
        [release_name] = [name for name in self.releases() if name != ACTIVE]
        release = self.news / "releases" / release_name
        self.assertTrue(release_name.startswith(REVISION + "-"))
        self.assertEqual((release / "REVISION").read_text(), REVISION + "\n")
        self.assertEqual((release / "news/schema.sql").read_bytes(), b"-- schema\n")
        self.assertTrue((release / "requirements.txt").is_file())
        self.assertFalse((release / "ops").exists())
        self.assertEqual(release.stat().st_mode & 0o777, 0o755)
        self.assertEqual((release / "news/__init__.py").stat().st_mode & 0o777, 0o644)
        installer, options = calls[0]
        self.assertEqual(installer[0], "systemd-run")
        self.assertIn("--wait", installer)
        self.assertNotIn("--pipe", installer)
        self.assertEqual(installer[-3:], ["/bin/sh", str(self.kit / "install-server"), str(release)])
        self.assertNotIn("SSH_ORIGINAL_COMMAND", options["env"])
        self.assertEqual(calls[1][0][0], "journalctl")

    def test_installer_failure_is_reported(self):
        self.installer_result = 1
        self.assertEqual(self.deploy()[0], 1)

    def test_kit_that_differs_from_the_revision_refuses_before_extracting(self):
        ops = checked_ops()
        ops["ops/install-server"] = b"#!/bin/sh\nid > /root/owned\n"
        code, calls, _, stderr = self.deploy(release_members(ops))
        self.assertEqual(code, 1)
        self.assertIn("does not match ops/ at " + REVISION, stderr)
        self.assertIn("bin/install-deploy-kit", stderr)
        self.assertFalse(calls)
        self.assertEqual(self.releases(), [ACTIVE])

    def test_new_or_removed_units_need_the_kit_first(self):
        ops = checked_ops()
        for change in ("added", "removed"):
            with self.subTest(change):
                changed = dict(ops)
                if change == "added":
                    changed["ops/systemd/news-extra.service"] = b"[Service]\nUser=root\n"
                else:
                    del changed["ops/systemd/news-backup.timer"]
                code, calls, _, stderr = self.deploy(release_members(changed))
                self.assertEqual(code, 1)
                self.assertIn("bin/install-deploy-kit", stderr)
                self.assertFalse(calls)

    def test_missing_installed_kit_refuses(self):
        for path in self.kit.iterdir():
            path.unlink()
        self.kit.rmdir()
        code, calls, _, stderr = self.deploy()
        self.assertEqual(code, 1)
        self.assertIn("bin/install-deploy-kit", stderr)
        self.assertFalse(calls)

    def test_unexpected_entry_in_the_installed_kit_refuses(self):
        (self.kit / "extra").mkdir()
        code, calls, _, stderr = self.deploy()
        self.assertEqual(code, 1)
        self.assertIn("Unexpected entry extra", stderr)
        self.assertFalse(calls)

    def test_archive_without_the_kit_files_refuses(self):
        ops = checked_ops()
        del ops["ops/build-environment"]
        code, calls, _, stderr = self.deploy(release_members(ops))
        self.assertEqual(code, 1)
        self.assertIn("ops/build-environment", stderr)
        self.assertFalse(calls)

    def test_rejects_every_other_ssh_command(self):
        for command in ("", "sh -c id", "id", "deploy", "deploy main", f"deploy {REVISION} x",
                        f"deploy {REVISION};id", "status x", "scp -t /root", "internal-sftp",
                        "/usr/lib/openssh/sftp-server"):
            with self.subTest(command=command):
                code, calls, stdout, stderr = self.receive(command, archive_bytes(release_members()))
                self.assertEqual(code, 1)
                self.assertIn("Refused", stderr)
                self.assertFalse(calls)
                self.assertEqual(stdout, "")
                self.assertEqual(self.releases(), [ACTIVE])

    def test_rejects_unsafe_archives_before_extracting(self):
        for name, extra in (
            ("parent", member("../escape", b"x")),
            ("absolute", member("/etc/escape", b"x")),
            ("outside the release", member(".env", b"x")),
            ("symbolic link", member("news/link", kind=tarfile.SYMTYPE, target="/etc")),
            ("hard link", member("news/hard", kind=tarfile.LNKTYPE, target="requirements.txt")),
            ("device", member("news/device", kind=tarfile.CHRTYPE)),
            ("setuid", member("news/tool", b"x", mode=0o4755)),
            ("repeated", member("news/schema.sql", b"-- other\n")),
        ):
            with self.subTest(name):
                code, calls, _, _ = self.deploy(release_members() + [extra])
                self.assertEqual(code, 1)
                self.assertFalse(calls)
                self.assertEqual(self.releases(), [ACTIVE])

    def test_incomplete_or_oversized_archives_are_refused(self):
        incomplete = [entry for entry in release_members() if entry[0].name != "news/schema.sql"]
        self.assertEqual(self.deploy(incomplete)[0], 1)
        with patch.object(self.receiver, "ARCHIVE_LIMIT", 1024):
            code, calls, _, stderr = self.deploy()
        self.assertEqual(code, 1)
        self.assertIn("exceeds", stderr)
        self.assertFalse(calls)
        self.assertEqual(self.releases(), [ACTIVE])

    def test_requires_root_and_supported_python(self):
        self.assertEqual(self.receive("status", uid=1000)[0], 1)
        with patch("sys.version_info", (3, 13, 0)):
            code, calls, _, _ = self.deploy()
        self.assertEqual(code, 1)
        self.assertFalse(calls)
        for version in ((3, 15, 0), (4, 0, 0)):
            with self.subTest(version=version), patch("sys.version_info", version):
                self.assertEqual(self.receive("status")[0], 0)

    def test_memory_pressure_while_parsing_is_a_clean_refusal(self):
        # A hostile archive that exhausts memory must refuse, not crash, and change nothing.
        with patch.object(self.receiver, "checked_members", side_effect=MemoryError):
            code, calls, _, stderr = self.deploy()
        self.assertEqual(code, 1)
        self.assertIn("news-receive-release", stderr)
        self.assertIn("memory", stderr)
        self.assertFalse(calls)
        self.assertEqual(self.releases(), [ACTIVE])

    @unittest.skipUnless(sys.platform == "linux", "RLIMIT_AS is enforced on the Linux production host")
    def test_address_space_cap_lowers_the_limit(self):
        import resource
        original = resource.getrlimit(resource.RLIMIT_AS)
        try:
            self.receiver.limit_address_space()
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            expected = (self.receiver.ADDRESS_SPACE_LIMIT if original[1] == resource.RLIM_INFINITY
                        else min(self.receiver.ADDRESS_SPACE_LIMIT, original[1]))
            self.assertEqual(soft, expected)
            self.assertEqual(hard, original[1])
        finally:
            resource.setrlimit(resource.RLIMIT_AS, original)


if __name__ == "__main__":
    unittest.main()
