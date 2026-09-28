"""Finite date lists through the newsroom and worker protocol."""

from datetime import date, timedelta
import json

from news.db import transaction
from support import ServerFixture


class ContractorTests(ServerFixture):
    dates = ["2026-10-01", "2026-10-03", "2026-10-05"]

    def history(self, reporter):
        response = self.client.get(
            f"/api/v1/worker/reporters/{reporter}/runs", headers=self.worker
        )
        self.assertEqual(response.status_code, 200)
        return response.json["runs"]

    def empty(self, run):
        body = self.envelope(
            self.claim(run), outcome="nothing_to_publish", articles=[], reason="No useful update"
        )
        response = self.result(run, body)
        self.assertEqual(response.status_code, 200)
        return body, response.json

    def fail_run(self, run):
        response = self.result(run, self.envelope(
            self.claim(run), outcome="failed", articles=[],
            error={"code": "research_failed", "message": "Source unavailable", "retryable": True},
        ))
        self.assertEqual(response.status_code, 200)

    def assert_active(self, reporter, active=True):
        html = self.client.get("/newsroom", headers=self.owner).get_data(as_text=True)
        self.assertEqual(f'/newsroom/reporters/{reporter}' in html, active)

    def test_october_four_catch_up_then_final_date_and_idempotent_publication(self):
        reporter = self.reporter("once", dates="\n".join(reversed(self.dates)))
        self.at("2026-10-04T06:00:00-07:00")
        run, = self.work()
        self.assertEqual(run["assignment_dates"], self.dates[:2])
        self.assertEqual(run["kind"], "catch_up")
        self.assertEqual(self.work()[0]["id"], run["id"])
        claim = self.claim(run["id"])
        self.assertEqual(claim["reporter"]["assignment_dates"], self.dates[:2])
        body = self.envelope(claim)
        receipt = self.result(run["id"], body)
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(self.result(run["id"], body).json, receipt.json)
        self.assertEqual(self.work(), [])
        self.assert_active(reporter)
        self.at("2026-10-05T06:00:00-07:00")
        last, = self.work()
        self.assertEqual(last["assignment_dates"], self.dates[2:])
        self.empty(last["id"])
        self.assert_active(reporter, False)
        self.assertEqual(self.work(), [])
        self.assertEqual(len(self.history(reporter)), 3)
        self.assertEqual(self.client.get("/api/v1/worker/articles/search", headers=self.worker).json["total"], 1)
        self.assertEqual(self.client.get("/articles/" + receipt.json["article_ids"][0]).status_code, 200)

    def test_october_five_includes_today_and_retires_after_empty_success(self):
        reporter = self.reporter("once", dates=self.dates)
        self.at("2026-10-05T06:00:00-07:00")
        run, = self.work()
        self.assertEqual(run["assignment_dates"], self.dates)
        body, receipt = self.empty(run["id"])
        self.assertEqual(self.result(run["id"], body).json, receipt)
        self.assertEqual(self.work(), [])
        self.assert_active(reporter, False)
        self.assertEqual({r["expected_date"] for r in self.history(reporter)}, set(self.dates))

    def test_exhausted_date_is_satisfied_by_later_success_with_failure_history(self):
        reporter = self.reporter("once", dates=self.dates)
        self.at("2026-10-01T06:00:00-07:00")
        first, = self.work()
        for hour in (6, 7, 8):
            self.at(f"2026-10-01T{hour:02}:00:00-07:00")
            self.fail_run(first["id"])
        for day in (1, 2):
            self.at(f"2026-10-0{day}T12:00:00-07:00")
            self.assertEqual(self.work(), [])
        self.assert_active(reporter)
        self.at("2026-10-03T06:00:00-07:00")
        later, = self.work()
        self.assertEqual(later["assignment_dates"], self.dates[:2])
        self.empty(later["id"])
        failed = next(r for r in self.history(reporter) if r["id"] == first["id"])
        self.assertEqual(failed["state"], "failed")
        self.assertEqual([a["outcome"] for a in failed["attempts"]], ["failed"] * 3)
        self.assertEqual(failed["satisfied_by_run_id"], later["id"])
        self.assertEqual(self.edit(reporter, cadence="once", dates=self.dates, prompt="New instructions").status_code, 303)
        self.assertEqual(self.work(), [])
        self.assert_active(reporter)
        self.at("2026-10-05T06:00:00-07:00")
        self.empty(self.work()[0]["id"])
        self.assert_active(reporter, False)

    def test_failed_catch_up_has_bounded_retries_and_instruction_recovery(self):
        reporter = self.reporter("once", dates=self.dates)
        self.at("2026-10-05T06:00:00-07:00")
        run, = self.work()
        self.fail_run(run["id"])
        self.assertEqual(self.work(), [])
        for day in (6, 7):
            self.at(f"2026-10-0{day}T06:00:00-07:00")
            self.assertEqual(self.work()[0]["id"], run["id"])
            self.fail_run(run["id"])
        self.at("2026-10-08T06:00:00-07:00")
        self.assertEqual(self.work(), [])
        self.assertEqual(self.edit(reporter, cadence="once", dates=self.dates).status_code, 303)
        self.assertEqual(self.work(), [])
        self.form(f"/newsroom/reporters/{reporter}/pause")
        self.form(f"/newsroom/reporters/{reporter}/resume")
        self.assertEqual(self.work(), [])
        self.assert_active(reporter)
        self.assertEqual(self.edit(reporter, cadence="once", dates=self.dates, prompt="Use the new source").status_code, 303)
        self.assertEqual(self.work()[0]["id"], run["id"])
        self.empty(run["id"])
        self.assertEqual(len(self.history(reporter)[0]["attempts"]), 4)
        self.assert_active(reporter, False)

    def test_pause_acknowledgment_then_resume_combines_unfinished_dates(self):
        reporter = self.reporter("once", dates=self.dates)
        self.form(f"/newsroom/reporters/{reporter}/pause")
        self.at("2026-10-04T06:00:00-07:00")
        run, = self.work()
        claim = self.claim(run["id"])
        self.assertTrue(claim["acknowledgment_only"])
        body = self.envelope(claim, outcome="skipped_paused", articles=[], reason="Paused")
        receipt = self.result(run["id"], body)
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(self.work(), [])
        self.assert_active(reporter)
        self.at("2026-10-05T06:00:00-07:00")
        self.form(f"/newsroom/reporters/{reporter}/resume")
        resumed, = self.work()
        self.assertEqual(resumed["assignment_dates"], self.dates)
        self.assertEqual(self.result(run["id"], body).json, receipt.json)
        self.empty(resumed["id"])
        self.assert_active(reporter, False)
        self.assertIn("skipped_paused", [a["outcome"] for r in self.history(reporter) for a in r["attempts"]])

    def test_active_attempt_scope_survives_new_due_dates_pause_and_future_edits(self):
        reporter = self.reporter("once", dates=self.dates)
        self.at("2026-10-01T06:00:00-07:00")
        run, = self.work()
        claim = self.claim(run["id"], request_id="fixed-claim", ownership_token="x" * 40)
        self.at("2026-10-04T06:00:00-07:00")
        dates = [*self.dates[:2], "2026-10-06"]
        self.assertEqual(self.edit(reporter, cadence="once", dates=dates).status_code, 303)
        self.form(f"/newsroom/reporters/{reporter}/pause")
        self.assertEqual(self.work()[0]["id"], run["id"])
        self.assertEqual(self.claim(run["id"], request_id="fixed-claim", ownership_token="x" * 40), claim)
        self.assertEqual(self.result(run["id"], self.envelope(claim)).status_code, 200)
        self.form(f"/newsroom/reporters/{reporter}/resume")
        later, = self.work()
        self.assertEqual(later["assignment_dates"], ["2026-10-03"])
        self.empty(later["id"])
        self.at("2026-10-05T06:00:00-07:00")
        self.assertEqual(self.work(), [])
        self.at("2026-10-06T06:00:00-07:00")
        self.empty(self.work()[0]["id"])
        self.assert_active(reporter, False)

    def test_validation_preview_and_future_only_edits_use_pacific_dates(self):
        for dates in ([], ["bad"], ["2026-10-01"] * 2, ["2026-09-25", "2026-10-01"]):
            with self.subTest(dates=dates):
                response = self.form("/newsroom/reporters", name="Bad dates", prompt="Report", cadence="once", dates=dates)
                self.assertEqual(response.status_code, 422)
        reporter = self.reporter("once", dates=self.dates)
        self.at("2026-10-02T00:30:00+00:00")  # Still October 1 in Pacific Time.
        self.assertEqual(self.edit(reporter, cadence="once", dates=self.dates[1:]).status_code, 409)
        dates = ["2026-10-01", "2026-10-02", "2026-10-06"]
        self.assertEqual(self.edit(reporter, cadence="once", dates=dates).status_code, 303)
        preview = self.client.get("/newsroom/schedule-preview", headers=self.owner, query_string={"cadence": "once", "dates": dates, "reporter_id": reporter})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json["next_date"], "2026-10-02")
        self.assertEqual(self.edit(reporter, cadence="once", dates=["2026-09-30", *dates]).status_code, 422)
        self.assertEqual(self.edit(reporter, cadence="daily").status_code, 422)
        self.assertEqual(self.work()[0]["assignment_dates"], ["2026-10-01"])

    def test_many_dates_and_legacy_single_date_data_keep_identity_and_history(self):
        dates = [(date(2026, 10, 1) + timedelta(days=i)).isoformat() for i in range(400)]
        preview = self.form("/newsroom/schedule-preview", cadence="once", dates="\n".join(dates))
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json["next_date"], dates[0])
        reporter = self.reporter("once", dates="\n".join(dates))
        self.at("2026-10-01T06:00:00-07:00")
        self.assertEqual(self.work()[0]["reporter"]["schedule"]["dates"], dates)
        # A pre-feature stored reporter is an external persistence fixture.
        legacy = self.reporter("once", date="2026-10-02")
        with transaction(self.database, write=True) as connection:
            connection.execute("UPDATE reporters SET schedule_json=? WHERE id=?", (json.dumps({"cadence": "once", "date": "2026-10-02"}), legacy))
        self.at("2026-10-02T06:00:00-07:00")
        run = next(r for r in self.work() if r["reporter_id"] == legacy)
        self.assertEqual(run["assignment_dates"], ["2026-10-02"])
        self.empty(run["id"])
        self.assert_active(legacy, False)
        self.assertEqual(self.history(legacy)[0]["expected_date"], "2026-10-02")

    def test_claim_from_history_satisfies_earlier_unstarted_dates(self):
        reporter = self.reporter("once", dates=self.dates)
        self.at("2026-10-03T06:00:00-07:00")
        self.assertEqual(self.app.test_cli_runner().invoke(args=["maintain"]).exit_code, 0)
        latest = self.history(reporter)[0]
        self.empty(latest["id"])
        self.assertEqual(self.work(), [])
        self.assert_active(reporter)
        self.assertEqual(self.history(reporter)[1]["state"], "superseded")

    def test_removing_last_future_date_after_success_retires_and_keeps_due_date(self):
        reporter = self.reporter("once", dates=self.dates)
        self.at("2026-10-01T06:00:00-07:00")
        self.empty(self.work()[0]["id"])
        self.assert_active(reporter)
        self.assertEqual(self.edit(reporter, cadence="once", dates=self.dates[:1]).status_code, 303)
        self.assert_active(reporter, False)
        self.assertEqual(self.history(reporter)[0]["state"], "nothing_to_publish")

    def test_legacy_active_snapshot_and_completed_history_survive_upgrade(self):
        reporter = self.reporter("once", date="2026-10-01")
        self.at("2026-10-01T06:00:00-07:00")
        run, = self.work()
        claim = self.claim(run["id"], request_id="legacy-claim", ownership_token="x" * 40)
        old_schedule = {"cadence": "once", "date": "2026-10-01"}
        old_snapshot = dict(claim["reporter"], schedule=old_schedule)
        old_snapshot.pop("assignment_dates")
        with transaction(self.database, write=True) as connection:
            connection.execute(
                "UPDATE reporters SET schedule_json=? WHERE id=?",
                (json.dumps(old_schedule), reporter),
            )
            connection.execute(
                "UPDATE run_attempts SET config_snapshot_json=? WHERE id=?",
                (json.dumps(old_snapshot), claim["attempt_id"]),
            )
        replay = self.claim(run["id"], request_id="legacy-claim", ownership_token="x" * 40)
        self.assertEqual(replay, dict(claim, reporter=old_snapshot))
        body = self.envelope(replay)
        receipt = self.result(run["id"], body)
        self.assertEqual(receipt.status_code, 200)
        self.assert_active(reporter, False)
        self.assertEqual(self.result(run["id"], body).json, receipt.json)
        detail = self.client.get(f"/newsroom/reporters/{reporter}", headers=self.owner)
        self.assertEqual(detail.status_code, 200)
        self.assertIn("2026-10-01", detail.get_data(as_text=True))
        self.assertEqual(self.history(reporter)[0]["attempts"][0]["outcome"], "published")
