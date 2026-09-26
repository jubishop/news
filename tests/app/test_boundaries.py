"""Protocol boundaries, concurrent requests, and complete owner history."""

from concurrent.futures import ThreadPoolExecutor
import io
import json
import secrets

from support import ServerFixture


class BoundaryTests(ServerFixture):
    def test_malformed_protocol_values_are_client_errors(self):
        _, run = self.due()
        claim = self.claim(run)
        for extra in (
            {"attempt_id": []},
            {"articles": [self.article(summary=float("nan"))]},
            {"outcome": None},
            {"articles": {}},
            {"ownership_token": 17},
        ):
            with self.subTest(extra=extra):
                response = self.result(run, self.envelope(claim, **extra))
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.result(run, self.envelope(claim)).status_code, 200)

    def test_service_and_browser_identity_cannot_be_interchanged(self):
        for claims in ({"email": "owner@example.com"}, {"common_name": None}):
            response = self.client.post(
                "/api/v1/worker/check-ins",
                headers={"Cf-Access-Jwt-Assertion": self.token("worker-aud", **claims)},
                json={"request_id": "not-service"},
            )
            self.assertEqual(response.status_code, 403)
        for claims in (
            {"email": 123},
            {"email": "other@example.com"},
            {"email": "owner@example.com", "iss": "https://wrong.example.com"},
        ):
            response = self.client.get(
                "/newsroom",
                headers={"Cf-Access-Jwt-Assertion": self.token("owner-aud", **claims)},
            )
            self.assertIn(response.status_code, (401, 403))

    def test_concurrent_claims_and_identical_results_are_atomic(self):
        _, run = self.due()

        def claim(_):
            with self.app.test_client() as client:
                return client.post(
                    f"/api/v1/worker/runs/{run}/claim",
                    headers=self.worker,
                    json={
                        "request_id": secrets.token_hex(16),
                        "ownership_token": secrets.token_urlsafe(32),
                    },
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(claim, range(2)))
        self.assertEqual(
            sorted(response.status_code for response in responses), [200, 409]
        )
        claim = next(
            response.json for response in responses if response.status_code == 200
        )
        body = self.envelope(claim)

        def submit(_):
            with self.app.test_client() as client:
                return client.post(
                    f"/api/v1/worker/runs/{run}/result", headers=self.worker, json=body
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(submit, range(2)))
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(responses[0].json, responses[1].json)
        archive = self.client.get(
            "/api/v1/worker/articles/search", headers=self.worker
        ).json
        self.assertEqual(archive["total"], 1)

    def test_all_owner_articles_are_accessible_for_trash(self):
        reporter, run = self.due()
        claim = self.claim(run)
        first = self.result(
            run,
            self.envelope(
                claim,
                articles=[self.article(title=f"First story {i}") for i in range(20)],
            ),
        )
        self.assertEqual(first.status_code, 200)
        self.at("2026-09-27T12:00:00-07:00")
        run = self.work()[0]["id"]
        self.result(
            run,
            self.envelope(
                self.claim(run), articles=[self.article(title="Newest story")]
            ),
        )
        page = self.client.get(
            f"/newsroom/reporters/{reporter}?articles_page=2", headers=self.owner
        )
        self.assertEqual(page.status_code, 200)
        text = page.get_data(as_text=True)
        self.assertEqual(text.count("Move to Trash</button>"), 1)
        self.assertNotIn("Newest story", text)

    def test_healthy_worker_missing_result_emails_and_clears_on_completion(self):
        self.app.config.update(
            MONITOR_WORKER=True,
            MONITOR_START_DATE="2026-09-25",
            RESEND_API_KEY="fixture",
            ALERT_TO="owner@example.com",
        )
        _, run = self.due()
        claim = self.claim(run)
        sent = []

        def deliver(request, **kwargs):
            sent.append(json.loads(request.data))
            return io.BytesIO(b'{"id":"sent"}')

        self.http.side_effect = deliver
        self.at("2026-09-27T00:00:00-07:00")
        self.app.test_cli_runner().invoke(args=["maintain"])
        self.assertEqual(len(sent), 1)
        self.assertIn("run overdue", sent[0]["subject"])
        self.app.test_cli_runner().invoke(args=["maintain"])
        self.assertEqual(len(sent), 1)
        self.result(
            run,
            self.envelope(
                claim,
                outcome="nothing_to_publish",
                articles=[],
                reason="No useful news.",
            ),
        )
        self.assertNotIn(
            "assignment has not returned",
            self.client.get("/newsroom", headers=self.owner).get_data(as_text=True),
        )

    def test_due_contractor_keeps_one_assignment_and_original_date(self):
        reporter, run = self.due(cadence="once", date="2026-09-26")
        response = self.edit(reporter, cadence="once", date="2026-09-30")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            self.edit(
                reporter,
                cadence="once",
                date="2026-09-26",
                prompt="Updated useful instructions.",
            ).status_code,
            303,
        )
        self.at("2026-09-30T12:00:00-07:00")
        runs = self.work()
        self.assertEqual([row["id"] for row in runs], [run])
        self.assertEqual(runs[0]["reporter"]["next_date"], "2026-09-26")

    def test_next_due_skips_completed_today_but_keeps_pending_old_schedule(self):
        reporter, run = self.due()
        self.result(run, self.envelope(self.claim(run)))
        html = self.client.get("/newsroom", headers=self.owner).get_data(as_text=True)
        self.assertRegex(html, r"<dt>Next due</dt>\s*<dd>\s*2026-09-27\s*</dd>")
        self.at("2026-09-27T12:00:00-07:00")
        self.edit(reporter, cadence="weekly", weekdays=["fri"])
        html = self.client.get("/newsroom", headers=self.owner).get_data(as_text=True)
        self.assertRegex(html, r"<dt>Next due</dt>\s*<dd>\s*2026-09-27\s*</dd>")
