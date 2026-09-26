"""Validate systemd syntax on Linux without installing units or starting services."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(
    shutil.which("systemd-analyze"), "systemd unit validation runs on Linux CI"
)
class UnitTests(unittest.TestCase):
    def test_systemd_units_parse(self):
        source = Path(__file__).resolve().parents[2] / "ops/systemd"
        with tempfile.TemporaryDirectory() as directory:
            targets = []
            for path in source.iterdir():
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
