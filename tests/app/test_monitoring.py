"""Calendar monitoring and outbound email through the server's public CLI."""

import io
import json
from urllib.error import URLError

from support import ServerFixture


class MonitoringTests(ServerFixture):
    def test_outage_groups_reports_and_recovers_without_daily_reminders(self):
        self.app.config.update(
            MONITOR_WORKER=True,
            MONITOR_START_DATE="2026-09-25",
            RESEND_API_KEY="fixture",
            ALERT_TO="owner@example.com",
        )
        self.reporter()
        self.reporter()
        self.at("2026-09-27T00:00:00-07:00")
        messages = []

        def send(request, **kwargs):
            messages.append(request)
            return io.BytesIO(b'{"id":"accepted"}')

        self.http.side_effect = send
        for day in (27, 28, 29):
            self.at(f"2026-09-{day}T12:00:00-07:00")
            result = self.app.test_cli_runner().invoke(args=["maintain"])
            self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(len(messages), 1)
        self.assertIn("worker missing", json.loads(messages[0].data)["subject"])
        self.work()
        self.at("2026-10-01T00:00:00-07:00")
        self.app.test_cli_runner().invoke(args=["maintain"])
        self.assertEqual(len(messages), 2)
        self.assertNotEqual(
            messages[0].get_header("Idempotency-key"),
            messages[1].get_header("Idempotency-key"),
        )

    def test_notification_retry_uses_frozen_payload_and_stops_after_safe_window(self):
        self.app.config.update(
            MONITOR_WORKER=True,
            MONITOR_START_DATE="2026-09-25",
            RESEND_API_KEY="fixture",
            ALERT_TO="owner@example.com",
        )
        self.at("2026-09-27T12:00:00-07:00")
        messages = []

        def fail(request, **kwargs):
            messages.append(request)
            raise URLError("fixture private response must not be logged")

        self.http.side_effect = fail
        for hour in (12, 13):
            self.at(f"2026-09-27T{hour}:00:00-07:00")
            self.app.test_cli_runner().invoke(args=["maintain"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].data, messages[1].data)
        self.assertEqual(
            messages[0].get_header("Idempotency-key"),
            messages[1].get_header("Idempotency-key"),
        )
        self.at("2026-09-28T12:00:00-07:00")
        self.app.test_cli_runner().invoke(args=["maintain"])
        self.assertEqual(len(messages), 2)
        self.assertIn(
            "reconcile with Resend",
            self.client.get("/newsroom", headers=self.owner).get_data(as_text=True),
        )

    def test_pacific_day_deadline_across_daylight_saving(self):
        self.at("2026-10-31T12:00:00-07:00")
        reporter = self.reporter()
        self.at("2026-11-01T00:00:00-07:00")
        run = self.work()[0]
        self.at("2026-11-01T23:59:59-08:00")
        self.app.test_cli_runner().invoke(args=["maintain"])
        history = self.client.get(
            f"/api/v1/worker/reporters/{reporter}/runs", headers=self.worker
        ).json["runs"]
        self.assertFalse(next(row for row in history if row["id"] == run["id"])["late"])
        self.at("2026-11-02T00:00:00-08:00")
        self.app.test_cli_runner().invoke(args=["maintain"])
        history = self.client.get(
            f"/api/v1/worker/reporters/{reporter}/runs", headers=self.worker
        ).json["runs"]
        self.assertTrue(next(row for row in history if row["id"] == run["id"])["late"])

    def test_crash_on_last_attempt_exhausts_allowance(self):
        reporter, run = self.due(cadence="once", date="2026-09-26")
        attempt = self.claim(run)
        for _ in range(2):
            attempt = self.claim(run, replace_attempt_id=attempt["attempt_id"])
        self.at("2026-09-27T12:00:00-07:00")
        maintenance = self.app.test_cli_runner().invoke(args=["maintain"])
        self.assertEqual(maintenance.exit_code, 0, maintenance.output)
        self.assertIn(
            "assignment has not returned",
            self.client.get("/newsroom", headers=self.owner).get_data(as_text=True),
        )
        response = self.client.post(
            f"/api/v1/worker/runs/{run}/claim",
            headers=self.worker,
            json={
                "request_id": "last-replacement",
                "ownership_token": "x" * 40,
                "replace_attempt_id": attempt["attempt_id"],
            },
        )
        self.assertEqual(response.status_code, 409)
        history = self.client.get(
            f"/api/v1/worker/reporters/{reporter}/runs", headers=self.worker
        ).json["runs"]
        self.assertEqual(history[0]["state"], "failed")
        self.assertEqual(self.work(), [])
        html = self.client.get("/newsroom", headers=self.owner).get_data(as_text=True)
        self.assertNotIn("assignment has not returned", html)
        self.assertIn("exhausted its attempts", html)

    def test_later_recurring_success_resolves_earlier_failure_notice(self):
        reporter, run = self.due()
        self.result(
            run,
            self.envelope(
                self.claim(run),
                outcome="failed",
                articles=[],
                error={
                    "code": "no_source",
                    "message": "Research failed.",
                    "retryable": False,
                },
            ),
        )
        html = self.client.get("/newsroom", headers=self.owner).get_data(as_text=True)
        self.assertIn("reported a final failure", html)
        self.at("2026-09-27T12:00:00-07:00")
        run = self.work()[0]["id"]
        self.result(
            run,
            self.envelope(
                self.claim(run),
                outcome="nothing_to_publish",
                articles=[],
                reason="No useful news.",
            ),
        )
        self.assertNotIn(
            "reported a final failure",
            self.client.get("/newsroom", headers=self.owner).get_data(as_text=True),
        )
        history = self.client.get(
            f"/api/v1/worker/reporters/{reporter}/runs", headers=self.worker
        ).json["runs"]
        self.assertEqual(
            [row["state"] for row in history], ["nothing_to_publish", "failed"]
        )
