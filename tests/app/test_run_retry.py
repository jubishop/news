"""Owner and worker retries of exhausted runs."""

import sqlite3
import unittest

from support import ServerFixture


class RunRetryTests(ServerFixture):
    def fail_attempt(self, run, claim):
        response = self.result(
            run,
            self.envelope(
                claim,
                outcome="failed",
                articles=[],
                error={
                    "code": "research_failed",
                    "message": "Spend limit reached",
                    "retryable": True,
                },
            ),
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.clock.return_value += 16 * 60

    def exhaust(self, run, attempts=3):
        for _ in range(attempts):
            self.fail_attempt(run, self.claim(run))

    def stored(self, run):
        with sqlite3.connect(self.database) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM runs WHERE id=?", (run,)).fetchone()
            notice = connection.execute(
                "SELECT resolved_at FROM incidents WHERE incident_key=?",
                ("failed:" + run,),
            ).fetchone()
        return dict(row), notice and notice["resolved_at"]

    def page(self, path):
        return self.client.get(path, headers=self.owner).get_data(as_text=True)

    def test_owner_retry_reopens_an_exhausted_run_with_a_fresh_allowance(self):
        reporter, run = self.due()
        self.exhaust(run)
        self.assertEqual(self.work(), [])
        action = f'action="/newsroom/runs/{run}/retry"'
        self.assertIn(action, self.page("/newsroom"))
        self.assertIn(action, self.page("/newsroom/reporters/" + reporter))

        response = self.form(f"/newsroom/runs/{run}/retry")
        self.assertEqual(response.status_code, 303, response.get_data(as_text=True))
        self.assertTrue(response.headers["Location"].endswith("/newsroom/reporters/" + reporter))
        row, resolved = self.stored(run)
        self.assertEqual((row["state"], row["retry_generation"]), ("pending", 2))
        self.assertIsNone(row["finished_at"])
        self.assertIsNotNone(resolved)
        page = self.page("/newsroom/reporters/" + reporter)
        self.assertIn("Retry queued", page)
        self.assertNotIn(action, page)
        for number in (1, 2, 3):
            self.assertIn(f"Attempt {number}</strong>", page)

        self.assertEqual(self.form(f"/newsroom/runs/{run}/retry").status_code, 409)
        self.assertEqual(self.stored(run)[0]["retry_generation"], 2)

        self.assertEqual([job["id"] for job in self.work()], [run])
        claim = self.claim(run)
        self.assertEqual(claim["attempt_number"], 4)
        self.fail_attempt(run, claim)
        self.exhaust(run, attempts=2)
        self.assertEqual(self.stored(run)[0]["state"], "failed")
        self.assertEqual(self.work(), [])

    def test_retry_is_refused_for_paused_removed_missing_and_older_runs(self):
        reporter = self.reporter()
        removed = self.reporter()
        self.at("2026-09-26T12:00:00-07:00")
        jobs = {job["reporter"]["id"]: job["id"] for job in self.work()}
        run, removed_run = jobs[reporter], jobs[removed]
        self.exhaust(run)
        self.exhaust(removed_run)

        self.assertEqual(self.form(f"/newsroom/reporters/{reporter}/pause").status_code, 303)
        self.assertNotIn(f"/newsroom/runs/{run}/retry", self.page("/newsroom/reporters/" + reporter))
        self.assertEqual(self.form(f"/newsroom/runs/{run}/retry").status_code, 409)
        self.assertEqual(self.form(f"/newsroom/reporters/{reporter}/resume").status_code, 303)
        self.assertIn(f"/newsroom/runs/{run}/retry", self.page("/newsroom/reporters/" + reporter))

        self.assertEqual(self.form(f"/newsroom/reporters/{removed}/delete").status_code, 303)
        self.assertEqual(self.form(f"/newsroom/runs/{removed_run}/retry").status_code, 409)
        self.assertEqual(self.form("/newsroom/runs/" + "0" * 32 + "/retry").status_code, 404)

        # The daily reporter is due again before the worker records that run.
        self.at("2026-09-27T05:00:00-07:00")
        self.assertNotIn(f"/newsroom/runs/{run}/retry", self.page("/newsroom/reporters/" + reporter))
        self.assertNotIn(f"/newsroom/runs/{run}/retry", self.page("/newsroom"))
        self.assertEqual(self.form(f"/newsroom/runs/{run}/retry").status_code, 409)
        self.assertEqual(self.stored(run)[0]["state"], "failed")

    def test_worker_retry_reopens_each_eligible_failure_once(self):
        eligible, run = self.due(cadence="weekly", weekdays=["sat"])
        self.exhaust(run)
        paused = self.reporter()
        self.at("2026-09-27T12:00:00-07:00")
        paused_run, = [job["id"] for job in self.work() if job["reporter"]["id"] == paused]
        self.exhaust(paused_run)
        self.assertEqual(self.form(f"/newsroom/reporters/{paused}/pause").status_code, 303)

        response = self.client.post("/api/v1/worker/retries", headers=self.worker, json={})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.json["runs"], [{
            "id": run, "reporter_id": eligible, "reporter_name": "Science desk",
            "expected_date": "2026-09-26", "retry_generation": 2,
        }])
        self.assertIsNotNone(self.stored(run)[1])
        again = self.client.post("/api/v1/worker/retries", headers=self.worker, json={})
        self.assertEqual(again.json["runs"], [])
        self.assertEqual(self.stored(paused_run)[0]["state"], "failed")
        self.assertEqual([job["reporter"]["id"] for job in self.work()], [eligible])
        self.assertEqual(
            self.client.post("/api/v1/worker/retries", headers=self.owner, json={}).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
