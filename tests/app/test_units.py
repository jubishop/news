"""Validate systemd units without installing them or starting services."""

from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

from gunicorn.config import Config


SOURCE = Path(__file__).resolve().parents[2] / "ops/systemd"


class WebUnitTests(unittest.TestCase):
    def test_gunicorn_opens_no_control_socket(self):
        # The default socket lives in the account's home. Ubuntu's built-in news
        # account uses /var/spool/news, which ProtectSystem=strict makes read-only.
        unit = (SOURCE / "news.service").read_text()
        command = shlex.split(re.search(r"^ExecStart=(.*)$", unit, re.M)[1])
        self.assertTrue(command[0].endswith("/gunicorn"))
        settings = Config().parser().parse_args(command[1:])
        self.assertTrue(settings.control_socket_disable)


@unittest.skipUnless(
    shutil.which("systemd-analyze"), "systemd unit validation runs on Linux CI"
)
class UnitTests(unittest.TestCase):
    def test_systemd_units_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            targets = []
            for path in SOURCE.iterdir():
                target = Path(directory) / path.name
                # The target release's interpreter does not exist on a CI host.
                value = re.sub(
                    r"^ExecStart=.*$",
                    "ExecStart=/usr/bin/true",
                    path.read_text(),
                    flags=re.M,
                )
                target.write_text(value)
                targets.append(str(target))
            result = subprocess.run(
                ["systemd-analyze", "verify", "--man=no", *targets],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
