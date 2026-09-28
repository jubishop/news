"""Reporter skill CLI journeys, with SSH replaced at the process boundary."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from support import ServerFixture


class ReporterSkillTests(ServerFixture):
    def setUp(self):
        super().setUp()
        self.root = Path(__file__).resolve().parents[2]
        self.helper = self.root / ".agents/skills/news-reporters/scripts/reporters.py"
        self.directory = Path(self.database).parent
        self.backups = self.directory / "backups"
        self.fake_bin = self.directory / "bin"
        self.fake_bin.mkdir()
        ssh = self.fake_bin / "ssh"
        ssh.write_text(f"#!{sys.executable}\n" + '''
import json
import os
import shlex
import subprocess
import sys

assert sys.argv[-2] == "fixture.test"
assert "StrictHostKeyChecking=yes" in sys.argv
command = shlex.split(sys.argv[-1])
assert command[:4] == ["runuser", "-u", "news", "--"]
assert command[-2] == "-c"
request = sys.stdin.read()
assert json.loads(request)["database"] == os.environ["FIXTURE_DATABASE"]
source = "import time\\ntime.time = lambda: " + os.environ["FIXTURE_NOW"] + "\\n" + command[-1]
result = subprocess.run([sys.executable, "-B", "-c", source], input=request, text=True, capture_output=True)
if os.environ.get("FIXTURE_LOST_REPLY") == "1":
    sys.exit(255)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
''')
        ssh.chmod(0o700)

    def run_helper(self, *args, values=None, status=0, lost_reply=False):
        command = [sys.executable, "-B", str(self.helper),
                   "--host", "fixture.test", "--release", str(self.root),
                   "--database", self.database, "--backup-dir", str(self.backups), *args]
        if values is not None:
            command.extend(["--data", "-"])
        result = subprocess.run(
            command, input=json.dumps(values) if values is not None else None,
            text=True, capture_output=True,
            env=dict(os.environ, PATH=str(self.fake_bin) + os.pathsep + os.environ["PATH"],
                     FIXTURE_DATABASE=self.database, FIXTURE_NOW=str(self.clock.return_value),
                     FIXTURE_LOST_REPLY="1" if lost_reply else "0"),
        )
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def create(self, **extra):
        return self.run_helper("create", values={
            "name": "Seahawks", "prompt": "Report on the latest completed game.",
            "cadence": "once", "dates": ["2026-10-03", "2026-10-01"], **extra,
        })

    def test_create_inspect_edit_and_backup_preserve_other_reporters(self):
        other = self.reporter()
        original = self.run_helper("show", other)["reporter"]
        self.assertFalse(self.backups.exists())
        prompt = "Use the coach's remarks.\nKeep `code` and $(text) literal."
        created = self.create(prompt=prompt)
        reporter = created["after"]
        self.assertTrue(created["verified"])
        self.assertEqual(reporter["schedule"], {"cadence": "once", "dates": ["2026-10-01", "2026-10-03"]})
        self.assertEqual(reporter["prompt"], prompt)
        self.assertEqual(reporter["next_date"], "2026-10-01")
        backup = Path(created["backup_path"])
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.backups.stat().st_mode & 0o777, 0o700)
        with sqlite3.connect(backup) as db:
            self.assertEqual(db.execute("SELECT id FROM reporters").fetchall(), [(other,)])
            self.assertEqual(db.execute("PRAGMA quick_check").fetchone()[0], "ok")
        edited = self.run_helper("update", reporter["id"], "--if-version", "1",
                                 values={"prompt": "Add injury updates."})
        self.assertEqual(edited["before"], reporter)
        self.assertEqual(edited["after"]["config_version"], 2)
        self.assertEqual(edited["after"]["schedule"], reporter["schedule"])
        self.assertEqual(edited["after"]["name"], reporter["name"])
        self.assertEqual(self.run_helper("show", other)["reporter"], original)
        roster = self.run_helper("list")["reporters"]
        self.assertEqual({row["id"] for row in roster}, {other, reporter["id"]})
        self.assertNotIn("prompt", roster[0])
        page = self.client.get("/newsroom/reporters/" + reporter["id"], headers=self.owner)
        self.assertIn("Add injury updates.", page.get_data(as_text=True))

    def test_invalid_and_stale_changes_leave_saved_configuration_intact(self):
        reporter = self.create()["after"]
        identity = reporter["id"]
        failures = [
            ({"dates": ["2026-09-25"]}, "1", "invalid_request"),
            ({"cadence": "daily"}, "1", "invalid_request"),
            ({"promt": "typo"}, "1", "invalid_request"),
            ({"name": "Changed"}, "7", "stale_version"),
        ]
        for values, version, error in failures:
            with self.subTest(values=values):
                result = self.run_helper("update", identity, "--if-version", version,
                                         values=values, status=1)
                self.assertEqual(result["error"], error)
                self.assertFalse(result["committed"])
                self.assertEqual(self.run_helper("show", identity)["reporter"], reporter)
        duplicate = self.run_helper("create", values={
            "name": "seahawks", "prompt": "Other coverage", "cadence": "daily",
        }, status=1)
        self.assertEqual(duplicate["error"], "duplicate_name")
        other = self.reporter()
        duplicate = self.run_helper("update", other, "--if-version", "1",
                                     values={"name": "Seahawks"}, status=1)
        self.assertEqual(duplicate["error"], "duplicate_name")

    def test_pause_resume_delete_keep_publication_and_active_work(self):
        identity = self.reporter()
        self.at("2026-09-26T06:00:00-07:00")
        run, = self.work()
        claim = self.claim(run["id"])
        paused = self.run_helper("pause", identity, "--if-version", "1")["after"]
        self.assertTrue(paused["paused"])
        resumed = self.run_helper("resume", identity, "--if-version", "2")["after"]
        self.assertFalse(resumed["paused"])
        deleted = self.run_helper("delete", identity, "--if-version", "3")["after"]
        self.assertIsNotNone(deleted["deleted_at"])
        result = self.result(run["id"], self.envelope(claim))
        self.assertEqual(result.status_code, 200)
        article_id, = result.json["article_ids"]
        self.assertEqual(self.client.get("/articles/" + article_id).status_code, 200)
        self.assertNotIn(identity, {r["id"] for r in self.run_helper("list")["reporters"]})
        self.assertIn(identity, {r["id"] for r in self.run_helper("list", "--all")["reporters"]})
        self.assertEqual(self.run_helper("show", identity)["reporter"]["deleted_at"], deleted["deleted_at"])
        result = self.run_helper("resume", identity, "--if-version", "4", status=1)
        self.assertEqual(result["error"], "retired")

    def test_due_dates_survive_edits_and_lost_reply_does_not_repeat_creation(self):
        values = {"name": "Seahawks", "prompt": "Game report", "cadence": "once",
                  "dates": ["2026-10-01", "2026-10-03"]}
        result = self.run_helper("create", values=values, status=1, lost_reply=True)
        self.assertEqual(result["error"], "outcome_unknown")
        reporter, = self.run_helper("list")["reporters"]
        self.at("2026-10-02T00:30:00+00:00")  # October 1 in Pacific Time.
        result = self.run_helper("update", reporter["id"], "--if-version", "1",
                                 values={"dates": ["2026-10-03"]}, status=1)
        self.assertEqual(result["error"], "assignment_due")
        edited = self.run_helper("update", reporter["id"], "--if-version", "1",
                                 values={"dates": ["2026-10-01", "2026-10-04"]})["after"]
        self.assertEqual(edited["schedule"]["dates"], ["2026-10-01", "2026-10-04"])
        run, = self.work()
        self.assertEqual(run["assignment_dates"], ["2026-10-01"])

    def test_backup_failure_prevents_mutation_and_missing_database_is_not_created(self):
        identity = self.reporter()
        original = self.run_helper("show", identity)["reporter"]
        self.backups.write_text("This path is a file, so no backup can be saved.")
        result = self.run_helper("update", identity, "--if-version", "1",
                                 values={"name": "Changed"}, status=1)
        self.assertEqual(result["error"], "operation_failed")
        self.assertFalse(result["committed"])
        self.assertEqual(self.run_helper("show", identity)["reporter"], original)
        self.database = str(self.directory / "missing.sqlite3")
        result = self.run_helper("create", values={
            "name": "Another", "prompt": "Report", "cadence": "daily",
        }, status=1)
        self.assertFalse(result["committed"])
        self.assertFalse(Path(self.database).exists())
