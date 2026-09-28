"""Compatibility with the real server protocol; Cloudflare and Codex stay fake."""

import io
import json
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError
from urllib import request as http_request

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
        return super().external_http(request, **kwargs)


class WorkerContractTests(WorkerHTTPFixture):
    def test_real_api_receives_agent_article_and_renders_it_publicly(self):
        reporter = self.reporter()
        self.at("2026-09-27T06:00:00-07:00")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "codex"
            article = self.article(title="From the reporting worker")
            executable.write_text(f"#!{sys.executable}\n" + f'''
import json, pathlib, sys
if "--version" in sys.argv:
    print("codex-cli 0.157.1")
elif "login" in sys.argv:
    print("Logged in using ChatGPT")
else:
    prompt = sys.stdin.read()
    assignment = json.loads(prompt.split("Assignment JSON:\\n", 1)[1])
    assert assignment["reporter"]["id"] == {reporter!r}
    assert assignment["expected_date"] == "2026-09-27"
    output = pathlib.Path(sys.argv[sys.argv.index("--output-last-message") + 1])
    output.write_text(json.dumps({{"outcome": "published", "articles": [{article!r}], "reason": "", "error": None}}))
''')
            executable.chmod(0o700)
            self.assertEqual(run({
                "server_url": "https://news.example.com", "client_id": "fixture-id",
                "client_secret": "fixture-secret", "state_dir": str(root / "state"),
                "codex": str(executable), "concurrency": 1, "qmd_command": fake_qmd(root),
            }), 0)
        self.assertIn("From the reporting worker", self.client.get("/").get_data(as_text=True))
        self.assertEqual(self.work(), [])
        history = self.client.get(f"/api/v1/worker/reporters/{reporter}/runs", headers=self.worker).json
        self.assertEqual(history["runs"][0]["state"], "published")
        self.assertEqual(history["runs"][0]["attempts"][0]["attempt_number"], 1)
