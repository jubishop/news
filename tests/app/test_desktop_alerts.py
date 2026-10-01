"""Local failure alerts with a real worker/server and fake OS executables."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

from news.desktop_alerts import notify
from news.worker import main, run
from test_worker_contract import WorkerHTTPFixture
from history_support import fake_qmd


class DesktopAlertTests(WorkerHTTPFixture):
    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory(prefix="news-alerts-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.sent = self.root / "notifications.jsonl"
        notifier = self.root / "notifier"
        notifier.write_text(f"#!{sys.executable}\n" + f'''
import json, pathlib, sys
with pathlib.Path({str(self.sent)!r}).open("a") as output:
    output.write(json.dumps({{"args": sys.argv[1:], "message": sys.stdin.read()}}) + "\\n")
''')
        notifier.chmod(0o700)
        codex = self.root / "codex"
        codex.write_text(f"#!{sys.executable}\n" + '''
import json, pathlib, sys
if "--version" in sys.argv:
    print("codex-cli 0.157.1")
elif "login" in sys.argv:
    print("Logged in using ChatGPT")
else:
    sys.stdin.read()
    output = pathlib.Path(sys.argv[sys.argv.index("--output-last-message") + 1])
    output.write_text(json.dumps({"outcome": "failed", "articles": [], "reason": None,
                                 "error": {"code": "research_failed", "message": "private detail", "retryable": True}}))
''')
        codex.chmod(0o700)
        self.settings = {
            "server_url": "https://news.example.com", "client_id": "fixture-id", "client_secret": "fixture-secret",
            "state_dir": str(self.root / "state"), "terminal_notifier": str(notifier),
            "codex": str(codex), "qmd_command": fake_qmd(self.root), "concurrency": 1,
        }

    def messages(self):
        return [json.loads(line) for line in self.sent.read_text().splitlines()] if self.sent.exists() else []

    def test_final_failure_notifies_immediately_once_without_polling(self):
        reporter, run_id = self.due()
        self.settings["retry_delay_seconds"] = 905

        def sleep(seconds):
            if seconds == 905:
                self.assertEqual(self.messages(), [], "No alerts while research retries remain")
                self.clock.return_value += seconds

        with patch("time.sleep", side_effect=sleep):
            self.assertEqual(run(self.settings), 1)
        message, = self.messages()
        self.assertIn("Science desk · 2026-09-26", message["message"])
        self.assertNotIn("private detail", message["message"])
        self.assertIn(f"https://news.example.com/newsroom/reporters/{reporter}", message["args"])
        history = self.client.get(f"/api/v1/worker/reporters/{reporter}/runs", headers=self.worker).json["runs"]
        self.assertEqual(history[0]["state"], "failed")
        self.assertEqual(len(history[0]["attempts"]), 3)
        self.assertEqual(run(self.settings), 0)
        self.assertEqual(len(self.messages()), 1)
        state = self.root / "state/alerts/seen.json"
        self.assertEqual(state.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("fixture-secret", state.read_text())

    def test_startup_error_notifies_once_and_healthy_batch_rearms(self):
        config = self.root / "worker.json"
        config.write_text(json.dumps({**self.settings, "concurrency": 99}))
        config.chmod(0o600)
        with patch("sys.argv", ["worker", "--config", str(config)]):
            self.assertEqual(main(), 1)
            self.assertEqual(main(), 1)
        self.assertEqual(len(self.messages()), 1)
        self.assertIn("News · Worker failed", self.messages()[0]["args"])
        self.assertEqual(run(self.settings), 0)
        with patch("sys.argv", ["worker", "--config", str(config)]):
            self.assertEqual(main(), 1)
        self.assertEqual(len(self.messages()), 2)

    def test_native_failure_does_not_break_reporting_or_mark_delivery(self):
        record = {"result": {"attempt_id": "attempt1"}, "run": {"expected_date": "2026-10-01"},
                  "claim": {"reporter": {"id": "reporter1", "name": "[Desk] $(private)"}}}
        with patch("news.desktop_alerts.subprocess.run", side_effect=subprocess.CalledProcessError(3, "notifier")):
            notify(self.settings, record=record)
        self.assertFalse((self.root / "state/alerts/seen.json").exists())
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: notify(self.settings, record=record), range(4)))
        notify(self.settings, record=record)
        self.assertEqual(len(self.messages()), 1)
        self.assertIn("[Desk] $(private)", self.messages()[0]["message"])

    def test_worker_alert_needs_no_working_api_or_credentials(self):
        notify({"state_dir": self.settings["state_dir"],
                "terminal_notifier": self.settings["terminal_notifier"]}, worker_failed=True)
        message, = self.messages()
        self.assertIn("News · Worker failed", message["args"])
        self.assertNotIn("-open", message["args"])

    def test_result_receipt_distinguishes_retry_wait_from_final_failure(self):
        _, run_id = self.due()
        for index in range(3):
            claim = self.claim(run_id)
            body = self.envelope(claim, outcome="failed", articles=[],
                                 error={"code": "research_failed", "message": "private detail", "retryable": True})
            response = self.result(run_id, body)
            self.assertEqual(response.json["run_state"], "failed" if index == 2 else "retry_wait")
            self.assertEqual(self.result(run_id, body).json, response.json)
            self.clock.return_value += 905
