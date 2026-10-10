"""Compatibility with the real server protocol; Cloudflare and Claude Code stay fake."""

from email.message import Message
import io
import json
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError
from urllib import request as http_request
from urllib.response import addinfourl

from news.worker import run
from support import ServerFixture
from history_support import fake_qmd

REAL_OPEN = http_request.OpenerDirector.open


class WorkerHTTPFixture(ServerFixture):
    def external_http(self, request, **kwargs):
        url = request if isinstance(request, str) else request.full_url
        prefix = "https://news.example.com"
        if url.startswith("http://127.0.0.1:"):
            return REAL_OPEN(http_request.build_opener(), request, **kwargs)
        if url.startswith(prefix):
            self.assertEqual(request.get_header("Cf-access-client-id"), "fixture-id")
            self.assertEqual(request.get_header("Cf-access-client-secret"), "fixture-secret")
            response = self.client.open(
                url.removeprefix(prefix), method=request.get_method(),
                headers=self.worker, data=request.data, content_type="application/json",
            )
            if response.status_code >= 400:
                raise HTTPError(url, response.status_code, "server error", {}, io.BytesIO(response.data))
            return io.BytesIO(response.data)
        if url.startswith("https://images.example.com/"):
            headers = Message()
            headers["Content-Type"] = "image/jpeg"
            return addinfourl(io.BytesIO(b"\xff\xd8\xff"), headers, url, 200)
        return super().external_http(request, **kwargs)


class WorkerContractTests(WorkerHTTPFixture):
    def test_worker_receives_one_catch_up_with_all_contractor_dates(self):
        dates = ["2026-10-01", "2026-10-03", "2026-10-05"]
        reporter = self.reporter("once", dates=dates)
        self.at("2026-10-05T06:00:00-07:00")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "claude"
            executable.write_text(f"#!{sys.executable}\n" + f'''
import json, pathlib, sys
if "--version" in sys.argv:
    print("2.1.296 (Claude Code)")
elif sys.argv[1:3] == ["auth", "status"]:
    print(json.dumps({{"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}}))
else:
    assignment = json.loads(sys.stdin.read().split("Assignment JSON:\\n", 1)[1])
    assert assignment["reporter"]["assignment_dates"] == {dates!r}
    assert assignment["reporter"]["schedule"] == {{"cadence": "once", "dates": {dates!r}}}
    assert assignment["expected_date"] == "2026-10-05"
    assert assignment["run_kind"] == "catch_up"
    print(json.dumps({{"type": "system", "subtype": "init", "mcp_servers": [{{"name": "news_history", "status": "connected"}}]}}))
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": False, "structured_output": {{"outcome": "nothing_to_publish", "articles": [], "reason": "Nothing useful", "error": None}}}}))
''')
            executable.chmod(0o700)
            settings = {
                "server_url": "https://news.example.com", "client_id": "fixture-id",
                "client_secret": "fixture-secret", "state_dir": str(root / "state"),
                "claude": str(executable), "concurrency": 1, "qmd_command": fake_qmd(root),
            }
            self.assertEqual(run(settings), 0)
            self.assertEqual(run(settings), 0)
        history = self.client.get(f"/api/v1/worker/reporters/{reporter}/runs", headers=self.worker).json["runs"]
        self.assertEqual(sum(len(row["attempts"]) for row in history), 1)
        self.assertEqual(self.work(), [])

    def test_real_api_receives_agent_article_and_renders_it_publicly(self):
        reporter = self.reporter()
        self.at("2026-09-27T06:00:00-07:00")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "claude"
            article = self.article(
                title="From the reporting worker",
                coverage_start="2026-09-01T06:00:00-07:00",
                coverage_end="2026-10-01T01:00:00Z",
                body_markdown=(
                    "A family outing at the museum.\n\n"
                    "![Families exploring the museum](https://images.example.com/museum.jpg)\n\n"
                    "Photo: [Museum](https://example.com/visit)."
                ),
                lead_image={
                    "url": "https://images.example.com/hall.jpg", "alt": "The museum's main hall",
                    "credit": "Museum", "credit_url": "https://example.com/press",
                },
            )
            executable.write_text(f"#!{sys.executable}\n" + f'''
import json, pathlib, sys
if "--version" in sys.argv:
    print("2.1.296 (Claude Code)")
elif sys.argv[1:3] == ["auth", "status"]:
    print(json.dumps({{"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}}))
else:
    prompt = sys.stdin.read()
    assignment = json.loads(prompt.split("Assignment JSON:\\n", 1)[1])
    assert assignment["reporter"]["id"] == {reporter!r}
    assert assignment["expected_date"] == "2026-09-27"
    print(json.dumps({{"type": "system", "subtype": "init", "mcp_servers": [{{"name": "news_history", "status": "connected"}}]}}))
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": False, "structured_output": {{"outcome": "published", "articles": [{article!r}], "reason": "", "error": None}}}}))
''')
            executable.chmod(0o700)
            self.assertEqual(run({
                "server_url": "https://news.example.com", "client_id": "fixture-id",
                "client_secret": "fixture-secret", "state_dir": str(root / "state"),
                "claude": str(executable), "concurrency": 1, "qmd_command": fake_qmd(root),
            }), 0)
        feed = self.client.get("/").get_data(as_text=True)
        self.assertIn("From the reporting worker", feed)
        self.assertIn('src="https://images.example.com/hall.jpg"', feed)
        stored, = self.client.get("/api/v1/worker/articles/search", headers=self.worker).json["articles"]
        self.assertEqual(stored["body_markdown"], article["body_markdown"])
        self.assertEqual(stored["lead_image"], article["lead_image"])
        self.assertEqual(stored["coverage_start"], "2026-09-01")
        self.assertEqual(stored["coverage_end"], "2026-09-30")
        html = self.client.get("/articles/" + stored["id"]).get_data(as_text=True)
        self.assertIn('src="https://images.example.com/museum.jpg"', html)
        self.assertIn('src="https://images.example.com/hall.jpg"', html)
        self.assertIn('href="https://example.com/press"', html)
        self.assertIn('alt="Families exploring the museum"', html)
        self.assertIn('referrerpolicy="no-referrer"', html)
        self.assertIn('href="https://example.com/visit"', html)
        self.assertEqual(self.work(), [])
        history = self.client.get(f"/api/v1/worker/reporters/{reporter}/runs", headers=self.worker).json
        self.assertEqual(history["runs"][0]["state"], "published")
        self.assertEqual(history["runs"][0]["attempts"][0]["attempt_number"], 1)
