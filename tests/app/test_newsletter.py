"""The daily newsletter through the public CLI, with Resend faked at the network."""

from contextlib import closing
import io
import json
import sqlite3
from urllib.error import URLError

from news.db import migrate
from support import ServerFixture


class NewsletterTests(ServerFixture):
    def setUp(self):
        super().setUp()
        self.app.config.update(RESEND_API_KEY="fixture", ALERT_TO="owner@example.com")
        self.requests, self.failing = [], False
        self.http.side_effect = self.resend

    def resend(self, request, **kwargs):
        url = request if isinstance(request, str) else request.full_url
        if url != "https://api.resend.com/emails":
            return self.external_http(request, **kwargs)
        self.requests.append(request)
        if self.failing and request.get_header("Idempotency-key").startswith("news-newsletter/"):
            raise URLError("fixture network failure")
        return io.BytesIO(json.dumps({"id": f"receipt-{len(self.requests)}"}).encode())

    def newsletters(self):
        return [
            {**json.loads(request.data), "key": request.get_header("Idempotency-key")}
            for request in self.requests
            if request.get_header("Idempotency-key").startswith("news-newsletter/")
        ]

    def query(self, sql):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute(sql).fetchone()

    def maintain(self):
        result = self.app.test_cli_runner().invoke(args=["maintain"])
        self.assertEqual(result.exit_code, 0, result.output)

    def publish(self, run, *articles):
        response = self.result(
            run, self.envelope(self.claim(run), articles=list(articles))
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json["article_ids"]

    def fail(self, run, retryable):
        error = {"code": "fixture", "message": "Research failed.", "retryable": retryable}
        response = self.result(
            run, self.envelope(self.claim(run), outcome="failed", articles=[], error=error)
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def test_waits_for_every_due_run_then_sends_exactly_once(self):
        self.reporter()
        self.reporter()
        self.at("2026-09-26T05:00:00-07:00")
        self.maintain()
        self.at("2026-09-26T06:00:00-07:00")
        first, second = (run["id"] for run in self.work())
        self.maintain()
        attempt = self.claim(first)
        self.maintain()
        self.result(
            first,
            self.envelope(
                attempt,
                outcome="failed",
                articles=[],
                error={"code": "fixture", "message": "Busy.", "retryable": True},
            ),
        )
        self.maintain()
        self.at("2026-09-26T06:30:00-07:00")
        photo = {
            "url": "https://images.example.com/cells.jpg",
            "alt": "Cells under a microscope",
            "credit": "Example Lab",
            "credit_url": "https://example.com/lab",
        }
        [article] = self.publish(
            first,
            self.article(
                title="Cells & <circuits>",
                summary="Neurons <b>rewire</b> themselves.",
                lead_image=photo,
            ),
        )
        self.maintain()
        self.assertEqual(self.newsletters(), [])
        self.fail(second, retryable=False)
        self.maintain()
        self.at("2026-09-26T18:00:00-07:00")
        self.maintain()

        [message] = self.newsletters()
        self.assertEqual(message["key"], "news-newsletter/2026-09-26")
        self.assertEqual(message["to"], ["owner@example.com"])
        self.assertEqual(message["from"], "News <news@jubishop.com>")
        self.assertIn("Saturday, Sep 26", message["subject"])
        link = "https://news.example.com/articles/" + article
        html = message["html"]
        self.assertIn("Cells &amp; &lt;circuits&gt;", html)
        self.assertIn("Neurons &lt;b&gt;rewire&lt;/b&gt; themselves.", html)
        self.assertNotIn("<circuits>", html)
        self.assertIn('src="https://images.example.com/cells.jpg"', html)
        self.assertIn('alt="Cells under a microscope"', html)
        self.assertIn("Science desk", html)
        self.assertIn(f'href="{link}"', html)
        self.assertIn('href="https://news.example.com/"', html)
        self.assertIn('href="https://news.example.com/newsroom"', html)
        text = message["text"]
        for expected in (
            "Cells & <circuits>",
            "Neurons <b>rewire</b> themselves.",
            "Science desk",
            link,
            "https://news.example.com/newsroom",
            "https://news.example.com/",
        ):
            self.assertIn(expected, text)
        alerts = [
            json.loads(request.data)["subject"]
            for request in self.requests
            if request.get_header("Idempotency-key").startswith("news-incident/")
        ]
        self.assertEqual(alerts, ["News · run failed"])
        receipt = self.query(
            "SELECT receipt_id,article_ids_json FROM newsletters WHERE newsletter_date='2026-09-26'"
        )
        self.assertTrue(receipt[0].startswith("receipt-"))
        self.assertEqual(json.loads(receipt[1]), [article])

    def test_quiet_day_waits_for_check_in_and_keeps_late_articles_for_next_morning(self):
        self.reporter(cadence="once", date="2026-09-26")
        self.at("2026-09-26T06:00:00-07:00")
        [run] = self.work()
        self.fail(run["id"], retryable=False)
        self.maintain()
        self.assertEqual(self.newsletters(), [])
        self.at("2026-09-26T09:00:00-07:00")
        retried = self.form(f"/newsroom/runs/{run['id']}/retry")
        self.assertEqual(retried.status_code, 303, retried.get_data(as_text=True))
        [late] = self.publish(run["id"], self.article(title="A late dispatch"))
        self.maintain()
        self.assertEqual(self.newsletters(), [])

        self.at("2026-09-27T00:10:00-07:00")
        self.maintain()
        self.assertEqual(self.newsletters(), [])
        self.at("2026-09-27T06:00:00-07:00")
        self.assertEqual(self.work(), [])
        self.maintain()
        [message] = self.newsletters()
        self.assertEqual(message["key"], "news-newsletter/2026-09-27")
        self.assertIn("A late dispatch", message["html"])
        self.assertIn("https://news.example.com/articles/" + late, message["html"])
        self.assertNotIn("/newsroom", message["html"])
        self.assertNotIn("/newsroom", message["text"])

    def test_each_newsletter_has_only_later_articles_and_no_deleted_ones(self):
        _, run = self.due()
        kept, deleted = self.publish(
            run,
            self.article(title="Kept dispatch"),
            self.article(title="Withdrawn dispatch"),
        )
        self.form(f"/newsroom/articles/{deleted}/delete")
        self.maintain()
        self.at("2026-09-27T06:00:00-07:00")
        [run] = self.work()
        [later] = self.publish(run["id"], self.article(title="Next dispatch"))
        self.maintain()

        first, second = self.newsletters()
        self.assertIn(kept, first["html"])
        self.assertNotIn(deleted, first["html"] + second["html"])
        self.assertNotIn("Withdrawn dispatch", first["text"] + second["text"])
        self.assertIn(later, second["html"])
        self.assertNotIn(kept, second["html"])
        self.assertEqual(
            [first["key"], second["key"]],
            ["news-newsletter/2026-09-26", "news-newsletter/2026-09-27"],
        )

    def test_retry_reuses_saved_payload_and_key_then_stops_after_safe_window(self):
        _, run = self.due()
        [article] = self.publish(run, self.article(title="Retried dispatch"))
        self.failing = True
        self.maintain()
        self.at("2026-09-26T12:01:00-07:00")
        self.maintain()
        self.form(f"/newsroom/articles/{article}/delete")
        self.at("2026-09-26T12:05:00-07:00")
        self.maintain()
        first, second = [
            request
            for request in self.requests
            if request.get_header("Idempotency-key").startswith("news-newsletter/")
        ]
        self.assertEqual(first.data, second.data)
        self.assertEqual(
            first.get_header("Idempotency-key"), second.get_header("Idempotency-key")
        )
        self.assertIn("Retried dispatch", json.loads(first.data)["text"])

        self.at("2026-09-27T10:55:00-07:00")
        self.maintain()
        self.assertEqual(len(self.newsletters()), 3)
        self.at("2026-09-27T11:00:00-07:00")
        self.maintain()
        self.assertEqual(len(self.newsletters()), 3)
        error, receipt = self.query(
            "SELECT error,receipt_id FROM newsletters WHERE newsletter_date='2026-09-26'"
        )
        self.assertIn("reconcile with Resend", error)
        self.assertIsNone(receipt)

    def test_first_newsletter_starts_after_articles_from_before_the_release(self):
        _, run = self.due()
        self.publish(run, self.article(title="Archived dispatch"))
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(
                "DROP TABLE newsletters; DROP TABLE newsletter_state; PRAGMA user_version = 3;"
            )
        migrate(self.database)
        migrate(self.database)
        self.assertEqual(self.query("PRAGMA user_version"), (4,))
        self.maintain()
        self.assertEqual(self.newsletters(), [])
        self.at("2026-09-27T06:00:00-07:00")
        [run] = self.work()
        self.publish(run["id"], self.article(title="Fresh dispatch"))
        self.maintain()
        [message] = self.newsletters()
        self.assertIn("Fresh dispatch", message["text"])
        self.assertNotIn("Archived dispatch", message["text"])

    def test_nothing_is_assembled_without_email_configuration(self):
        self.app.config.update(RESEND_API_KEY="")
        _, run = self.due()
        self.publish(run, self.article())
        self.maintain()
        self.app.config.update(RESEND_API_KEY="fixture")
        self.at("2026-09-27T06:00:00-07:00")
        [run] = self.work()
        self.publish(run["id"], self.article(title="Second dispatch"))
        self.maintain()
        [message] = self.newsletters()
        self.assertEqual(message["key"], "news-newsletter/2026-09-27")
        self.assertIn("This week in research", message["text"])
        self.assertIn("Second dispatch", message["text"])
