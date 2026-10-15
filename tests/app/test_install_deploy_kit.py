"""Exercise the deploy kit installer with fake Git and SSH boundaries.

The fake host unpacks what the installer sends and answers with the digest
that ops/receive-release computes for an installed kit, so the installer and
the receiver must agree on the kit's files and digest.
"""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
REVISION = "a" * 40
FAKE_COMMAND = r"""#!/usr/bin/env python3
import hashlib, io, json, os, sys, tarfile
from pathlib import Path
name, args = Path(sys.argv[0]).name, sys.argv[1:]
base = Path(os.environ["FIXTURE"])
with (base / "calls").open("a") as log:
    log.write(json.dumps([name, *args]) + "\n")
if name == "git":
    if args[:2] == ["rev-parse", "--verify"]:
        if args[2] not in ("HEAD^{commit}", "a" * 40 + "^{commit}"):
            sys.exit(128)
        print("a" * 40)
    elif args == ["archive", "--format=tar", "a" * 40, "ops/"]:
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tree:
            tree.add(base / "checked/ops", arcname="ops")
    else:
        sys.exit(99)
elif name == "ssh":
    if os.environ.get("SSH_EXIT"):
        sys.exit(int(os.environ["SSH_EXIT"]))
    host = base / "host"
    host.mkdir()
    with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read())) as sent:
        modes = {member.name: member.mode for member in sent.getmembers()}
        sent.extractall(host, filter="data")
    (base / "modes.json").write_text(json.dumps(modes))
    # The receiver digests itself and the other kit files, as installed.
    files = {path.name: path.read_bytes() for path in host.iterdir()}
    listing = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items()))
    digest = os.environ.get("HOST_KIT") or hashlib.sha256(listing.encode()).hexdigest()
    print("Installed.")
    print(json.dumps({"active": "0" * 40, "kit": digest}))
"""


def load_installer():
    loader = SourceFileLoader("install_deploy_kit", str(ROOT / "bin/install-deploy-kit"))
    spec = spec_from_loader(loader.name, loader)
    assert spec
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


class InstallDeployKitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        (self.base / "bin").mkdir()
        shutil.copy2(ROOT / "bin/install-deploy-kit", self.base / "bin/install-deploy-kit")
        shutil.copytree(ROOT / "ops", self.base / "checked/ops")
        commands = self.base / "commands"
        commands.mkdir()
        (commands / "command").write_text(FAKE_COMMAND)
        (commands / "command").chmod(0o755)
        for name in ("git", "ssh"):
            (commands / name).symlink_to(commands / "command")
        self.environment = os.environ | {"FIXTURE": str(self.base),
                                         "PATH": str(commands) + os.pathsep + os.environ["PATH"]}

    def execute(self, *args, **environment):
        return subprocess.run([str(self.base / "bin/install-deploy-kit"), *args], cwd=self.base,
                              env=self.environment | environment, text=True, capture_output=True, timeout=30)

    def calls(self):
        path = self.base / "calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_installs_exactly_the_kit_from_git(self):
        # The working tree is not what gets installed.
        (self.base / "ops").mkdir()
        (self.base / "ops/install-server").write_text("echo unchecked working copy\n")
        result = self.execute("root@example.test", "HEAD")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Installed deploy kit", result.stdout)
        self.assertIn(REVISION, result.stdout)
        installed = {path.name: path.read_bytes() for path in (self.base / "host").iterdir()}
        checked = self.base / "checked/ops"
        expected = {name: (checked / name).read_bytes()
                    for name in ("receive-release", "install-server", "build-environment", "rebuild-environment")}
        expected |= {path.name: path.read_bytes() for path in (checked / "systemd").iterdir()}
        self.assertEqual(installed, expected)
        for name in ("deploy-main", "install-worker", "Caddyfile.fragment", "backup.env.example"):
            self.assertNotIn(name, installed)
        modes = json.loads((self.base / "modes.json").read_text())
        self.assertEqual(modes["receive-release"], 0o755)
        self.assertEqual(modes["rebuild-environment"], 0o755)
        self.assertEqual(modes["install-server"], 0o644)
        ssh = [call for call in self.calls() if call[0] == "ssh"]
        self.assertEqual(len(ssh), 1)
        self.assertIn("root@example.test", ssh[0])
        self.assertIn("BatchMode=yes", ssh[0])

    def test_host_reporting_another_kit_fails(self):
        result = self.execute("root@example.test", REVISION, HOST_KIT="c" * 64)
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match", result.stderr)
        self.assertNotIn("Installed deploy kit", result.stdout)

    def test_failed_installation_fails(self):
        result = self.execute("root@example.test", REVISION, SSH_EXIT="1")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Installed deploy kit", result.stdout)

    def test_bad_arguments_never_contact_the_host(self):
        for args in ((), ("root@example.test",), ("example.test", REVISION), ("root@-oProxyCommand=x", REVISION),
                     ("root@example.test", "unknown-revision"), ("root@example.test", REVISION, "extra")):
            with self.subTest(args=args):
                (self.base / "calls").unlink(missing_ok=True)
                result = self.execute(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(call[0] == "ssh" for call in self.calls()))

    def test_incomplete_kit_never_contacts_the_host(self):
        (self.base / "checked/ops/build-environment").unlink()
        result = self.execute("root@example.test", REVISION)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ops/build-environment", result.stderr)
        self.assertFalse(any(call[0] == "ssh" for call in self.calls()))

    def test_remote_installation_script_passes_shellcheck(self):
        if not shutil.which("shellcheck"):
            self.skipTest("ShellCheck is not installed.")
        result = subprocess.run(["shellcheck", "--shell=sh", "-"], input=load_installer().INSTALL,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout)


def can_be_root():
    if os.geteuid() == 0:
        return True
    return subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0


@unittest.skipUnless(sys.platform == "linux" and can_be_root(),
                     "Running the root install script needs a disposable root on Linux")
class InstallScriptTests(unittest.TestCase):
    """Run the real root INSTALL script in a chroot, against a fake receiver."""

    def setUp(self):
        self.prefix = [] if os.geteuid() == 0 else ["sudo", "-n"]
        self.root = Path(tempfile.mkdtemp())
        # The install script creates root-owned directories that only root can empty.
        self.addCleanup(subprocess.run, self.prefix + ["rm", "-rf", str(self.root)], check=True)
        for executable in ("sh", "tar", "install", "mktemp", "rm", "mv", "ln", "stat", "flock"):
            source = Path(shutil.which(executable)).resolve()
            for library in re.findall(r"(/[^\s()]+)", subprocess.check_output(["ldd", str(source)], text=True)):
                self.copy(Path(library), library)
            self.copy(source, "/bin/" + executable)
        for directory in ("usr/local/lib", "usr/local/sbin", "run/lock", "tmp", "etc"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        # The real `install -o root -g root` resolves these names in the chroot.
        (self.root / "etc/passwd").write_text("root:x:0:0:root:/root:/bin/sh\n")
        (self.root / "etc/group").write_text("root:x:0:\n")
        # A stale kit file that the new kit does not include must be removed.
        (self.root / "usr/local/lib/news-deploy").mkdir(parents=True)
        (self.root / "usr/local/lib/news-deploy/old-helper").write_text("stale\n")

    def copy(self, source, destination):
        target = self.root / destination.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)

    def install(self, kit):
        """Send a {name: (mode, bytes)} kit as a tar on stdin to the INSTALL script under chroot."""
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name, (mode, data) in sorted(kit.items()):
                member = tarfile.TarInfo(name)
                member.size, member.mode = len(data), mode
                archive.addfile(member, io.BytesIO(data))
        return subprocess.run(
            self.prefix + ["chroot", str(self.root), "/bin/sh", "-c", load_installer().INSTALL],
            input=stream.getvalue(),
            env=os.environ | {"PATH": "/bin:/usr/bin:/usr/sbin:/sbin"}, capture_output=True,
        )

    def test_places_kit_files_with_modes_and_removes_stale_ones(self):
        # A fake receiver avoids needing a Python interpreter in the chroot; it prints the final status.
        receiver = b'#!/bin/sh\n[ "$SSH_ORIGINAL_COMMAND" = status ] && echo \'{"active":null,"kit":"0"}\'\n'
        kit = {
            "receive-release": (0o755, receiver),
            "install-server": (0o644, b"# install-server\n"),
            "build-environment": (0o644, b"# build-environment\n"),
            "rebuild-environment": (0o755, b"# rebuild-environment\n"),
            "news.service": (0o644, b"# unit\n"),
        }
        result = self.install(kit)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        lib = self.root / "usr/local/lib/news-deploy"
        self.assertEqual((lib / "install-server").read_bytes(), b"# install-server\n")
        self.assertEqual((self.root / "usr/local/sbin/news-receive-release").read_bytes(), receiver)
        self.assertEqual(os.readlink(self.root / "usr/local/sbin/news-rebuild-environment"),
                         "/usr/local/lib/news-deploy/rebuild-environment")
        self.assertEqual((lib / "rebuild-environment").stat().st_mode & 0o777, 0o755)
        self.assertEqual((lib / "install-server").stat().st_mode & 0o777, 0o644)
        self.assertEqual((self.root / "usr/local/sbin/news-receive-release").stat().st_mode & 0o777, 0o755)
        # The receiver is not left behind in the kit directory, and the stale helper is gone.
        self.assertFalse((lib / "receive-release").exists())
        self.assertFalse((lib / "old-helper").exists())
        self.assertIn(b"Removed old-helper", result.stdout)
        self.assertIn(b'{"active":null,"kit":"0"}', result.stdout)


if __name__ == "__main__":
    unittest.main()
