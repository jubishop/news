"""Complete owner and worker HTTP journeys."""

import unittest

from support import ServerFixture


class ServerTests(ServerFixture):
    def test_public_reading_owner_auth_and_csrf_boundaries(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        for path in ["/newsroom", "/newsroom/trash", "/api/v1/worker/articles/search"]:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(
            self.client.get("/newsroom", headers=self.worker).status_code, 403
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/worker/articles/search", headers=self.owner
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/newsroom/reporters", headers=self.owner, data={}
            ).status_code,
            403,
        )
        for token in [
            self.token("owner-aud", email="stranger@example.com"),
            self.token("owner-aud", email="owner@example.com", exp=1),
        ]:
            self.assertIn(
                self.client.get(
                    "/newsroom", headers={"Cf-Access-Jwt-Assertion": token}
                ).status_code,
                (401, 403),
            )
        response = self.client.get(
            "/newsroom",
            headers={"Cf-Access-Authenticated-User-Email": "owner@example.com"},
        )
        self.assertEqual(response.status_code, 401)

    def test_schedule_starts_tomorrow_and_edits_preserve_today(self):
        reporter = self.reporter()
        self.assertEqual(self.work(), [])
        self.at("2026-09-26T12:00:00-07:00")
        run = self.work()[0]
        self.assertEqual(run["expected_date"], "2026-09-26")
        response = self.edit(reporter, cadence="weekly", weekdays="mon")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.work()[0]["id"], run["id"])
        claim = self.claim(run["id"])
        self.assertEqual(
            self.result(
                run["id"],
                self.envelope(
                    claim,
                    outcome="nothing_to_publish",
                    articles=[],
                    reason="Nothing new",
                ),
            ).status_code,
            200,
        )
        self.at("2026-09-27T12:00:00-07:00")
        self.assertEqual(self.work(), [])
        self.at("2026-09-28T12:00:00-07:00")
        self.assertEqual(self.work()[0]["expected_date"], "2026-09-28")

    def test_publication_is_atomic_idempotent_and_coverage_is_worker_supplied(self):
        reporter, run = self.due()
        claim = self.claim(run)
        invalid = self.envelope(
            claim, articles=[self.article(), self.article(coverage_end="2026-08-01")]
        )
        self.assertEqual(self.result(run, invalid).status_code, 422)
        self.assertEqual(
            self.client.get("/api/v1/worker/articles/search", headers=self.worker).json[
                "articles"
            ],
            [],
        )
        body = self.envelope(
            claim, articles=[self.article(), self.article(title="Second story")]
        )
        response = self.result(run, body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["article_ids"]), 2)
        self.assertEqual(self.result(run, body).json, response.json)
        altered = {**body, "articles": [self.article(title="Changed")]}
        self.assertEqual(self.result(run, altered).status_code, 409)
        article = self.client.get(
            "/api/v1/worker/articles/" + response.json["article_ids"][0],
            headers=self.worker,
        ).json
        self.assertEqual(article["coverage_end"], "2026-09-30")
        self.assertEqual(article["reporter_id"], reporter)
        self.assertIn("Second story", self.client.get("/").get_data(as_text=True))

    def test_prompt_snapshot_and_pause_after_claim_keep_finished_work(self):
        reporter, run = self.due()
        claim = self.claim(run)
        self.edit(reporter, prompt="A different beat")
        self.form(f"/newsroom/reporters/{reporter}/pause")
        self.assertIn("new research", claim["reporter"]["prompt"])
        self.assertEqual(self.result(run, self.envelope(claim)).status_code, 200)
        self.at("2026-09-27T12:00:00-07:00")
        run = self.work()[0]["id"]
        paused = self.claim(run)
        self.assertTrue(paused["acknowledgment_only"])
        self.assertEqual(self.result(run, self.envelope(paused)).status_code, 409)
        result = self.envelope(
            paused, outcome="skipped_paused", articles=[], reason="Reporter is paused"
        )
        self.assertEqual(self.result(run, result).status_code, 200)
        self.form(f"/newsroom/reporters/{reporter}/resume")
        self.assertEqual(self.work(), [])

    def test_incoming_work_survives_reporter_removal_but_new_claim_alerts(self):
        reporter, run = self.due()
        claim = self.claim(run)
        self.form(f"/newsroom/reporters/{reporter}/delete")
        body = self.envelope(claim)
        response = self.result(run, body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.result(run, body).json, response.json)
        rejected = self.client.post(
            f"/api/v1/worker/runs/{run}/claim",
            headers=self.worker,
            json={"request_id": "new-claim", "ownership_token": "a" * 40},
        )
        self.assertEqual(rejected.status_code, 409)
        self.assertIn(
            "removed reporter",
            self.client.get("/newsroom", headers=self.owner)
            .get_data(as_text=True)
            .lower(),
        )
        self.assertEqual(self.work(), [])
        self.assertEqual(
            self.client.get("/articles/" + response.json["article_ids"][0]).status_code,
            200,
        )

    def test_trash_restore_and_permanent_purge_do_not_republish_retries(self):
        _, run = self.due()
        body = self.envelope(self.claim(run))
        receipt = self.result(run, body).json
        article_id = receipt["article_ids"][0]
        self.form(f"/newsroom/articles/{article_id}/delete")
        self.assertEqual(self.client.get("/articles/" + article_id).status_code, 404)
        self.assertEqual(
            self.client.get(
                "/api/v1/worker/articles/" + article_id, headers=self.worker
            ).status_code,
            404,
        )
        self.assertEqual(
            self.form(f"/newsroom/articles/{article_id}/restore").status_code, 303
        )
        self.form(f"/newsroom/articles/{article_id}/delete")
        self.at("2026-10-26T12:00:00-07:00")
        self.assertEqual(
            self.form(f"/newsroom/articles/{article_id}/restore").status_code, 409
        )
        self.assertEqual(
            self.app.test_cli_runner().invoke(args=["maintain"]).exit_code, 0
        )
        self.assertNotIn(
            "This week in research",
            self.client.get("/newsroom/trash", headers=self.owner).get_data(
                as_text=True
            ),
        )
        self.assertEqual(self.result(run, body).json, receipt)
        self.assertEqual(self.client.get("/articles/" + article_id).status_code, 404)

    def test_contractor_stays_due_and_pause_does_not_complete_it(self):
        reporter = self.reporter("once", date="2026-09-26")
        self.at("2026-10-10T12:00:00-07:00")
        run = self.work()[0]
        self.assertEqual(run["expected_date"], "2026-09-26")
        self.form(f"/newsroom/reporters/{reporter}/pause")
        claim = self.claim(run["id"])
        self.result(
            run["id"],
            self.envelope(
                claim, outcome="skipped_paused", articles=[], reason="Paused"
            ),
        )
        self.form(f"/newsroom/reporters/{reporter}/resume")
        self.assertEqual(self.work()[0]["id"], run["id"])
        claim = self.claim(run["id"])
        self.result(
            run["id"],
            self.envelope(
                claim,
                outcome="nothing_to_publish",
                articles=[],
                reason="No longer timely",
            ),
        )
        self.assertEqual(self.work(), [])
        self.assertNotIn(
            "Science desk",
            self.client.get("/newsroom", headers=self.owner).get_data(as_text=True),
        )

    def test_missed_recurring_occurrences_become_one_catch_up(self):
        reporter = self.reporter()
        self.at("2026-10-01T12:00:00-07:00")
        runs = self.work()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["kind"], "catch_up")
        self.assertEqual(runs[0]["expected_date"], "2026-10-01")
        history = self.client.get(
            f"/api/v1/worker/reporters/{reporter}/runs", headers=self.worker
        ).json["runs"]
        self.assertEqual(sum(r["state"] == "superseded" for r in history), 5)

    def test_claim_retry_replacement_and_late_unreplaced_result(self):
        _, run = self.due()
        first = self.claim(run, request_id="stable-claim", ownership_token="x" * 40)
        same = self.claim(run, request_id="stable-claim", ownership_token="x" * 40)
        self.assertEqual(first, same)
        second = self.claim(run, replace_attempt_id=first["attempt_id"])
        self.assertEqual(self.result(run, self.envelope(first)).status_code, 409)
        self.at("2026-09-28T12:00:00-07:00")
        self.assertEqual(self.result(run, self.envelope(second)).status_code, 200)

    def test_failed_contractor_reopens_only_after_changed_instructions(self):
        reporter, run = self.due(cadence="once", date="2026-09-26")
        for day in (26, 27, 28):
            self.at(f"2026-09-{day}T12:00:00-07:00")
            claim = self.claim(run)
            response = self.result(
                run,
                self.envelope(
                    claim,
                    outcome="failed",
                    articles=[],
                    error={
                        "code": "research_failed",
                        "message": "Network unavailable",
                        "retryable": True,
                    },
                ),
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.work(), [])
        self.edit(reporter, cadence="once", date="2026-09-26")
        self.assertEqual(self.work(), [])
        self.edit(
            reporter, cadence="once", date="2026-09-26", prompt="Try the new source"
        )
        self.assertEqual(self.work()[0]["id"], run)
        self.assertEqual(self.claim(run)["attempt_number"], 4)

    def test_markdown_images_links_and_tables_are_safe(self):
        _, run = self.due()
        markdown = (
            "<script>alert(1)</script>\n\n[x](javascript:alert(1))\n\n"
            "![Safe](https://example.com/image.jpg)\n\n![Unsafe](http://example.com/image.jpg)\n\n"
            "| Name | Value |\n| --- | --- |\n| A | B |"
        )
        response = self.result(
            run,
            self.envelope(
                self.claim(run), articles=[self.article(body_markdown=markdown)]
            ),
        )
        html = self.client.get("/articles/" + response.json["article_ids"][0]).get_data(
            as_text=True
        )
        self.assertNotIn("<script>alert", html)
        self.assertNotIn('href="javascript:', html)
        self.assertNotIn('src="http://', html)
        self.assertIn('src="https://example.com/image.jpg"', html)
        self.assertIn("<table>", html)

    def test_month_end_preview_and_category_validation(self):
        response = self.client.get(
            "/newsroom/schedule-preview?cadence=monthly&day_of_month=31",
            headers=self.owner,
        )
        self.assertEqual(response.json["next_date"], "2026-09-30")
        self.at("2028-02-01T12:00:00-08:00")
        response = self.client.get(
            "/newsroom/schedule-preview?cadence=monthly&day_of_month=31",
            headers=self.owner,
        )
        self.assertEqual(response.json["next_date"], "2028-02-29")
        reporter = self.reporter()
        self.assertEqual(
            self.edit(reporter, cadence="once", date="2028-03-01").status_code, 422
        )
        self.assertEqual(
            self.form(
                "/newsroom/reporters",
                name="Bad",
                prompt="Bad",
                cadence="once",
                date="2028-02-01",
            ).status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
