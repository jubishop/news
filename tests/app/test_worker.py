"""The real supervisor between a mock HTTP newsroom and a fake Codex executable."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from news.worker import run
from history_support import fake_qmd

ARTICLE = {
    "title": "A verified development",
    "summary": "Useful news, with an explicit source.",
    "body_markdown": "Read the [primary source](https://example.com/story).",
    "article_date": "2026-09-27",
    "coverage_start": "2026-09-26",
    "coverage_end": "2026-09-27",
    "sources": [{"title": "Primary source", "url": "https://example.com/story"}],
}
RESULT = {"outcome": "published", "articles": [ARTICLE], "reason": "", "error": None}


class Newsroom:
    def __init__(self):
        self.requests = []
        self.results = []
        self.claims = {}
        self.receipts = {}
        self.lose_claim_responses = 0
        self.lose_result_responses = 0
        self.runs = []
        self.failures = {}
        self.truncated_responses = {}
        self.archive = [dict(ARTICLE, id="old", reporter_id="reporter0")]
        self.lock = threading.Lock()

    def add(self, number=0, paused=False):
        reporter = {
            "id": f"reporter{number}", "name": f"Reporter {number}",
            "prompt": "Exact instructions: café\nFind useful news; preserve ‘quotes’.",
            "schedule": {"cadence": "daily"}, "paused": paused, "config_version": 2,
        }
        self.runs.append({
            "id": f"run{number}", "reporter": reporter, "expected_date": "2026-09-27",
            "kind": "scheduled", "state": "pending", "current_attempt": None,
        })
        return reporter

    def respond(self, method, path, body):
        route = path.split("?", 1)[0].removeprefix("/api/v1/worker")
        with self.lock:
            self.requests.append((method, path, deepcopy(body)))
            failure = self.failures.get(route)
            if failure and failure[0] > 0:
                failure[0] -= 1
                return failure[1], {"error": "fixture_failure", "message": "Unavailable"}
            if route == "/check-ins":
                return 200, {"reporting_date": "2026-09-27", "runs": deepcopy(self.runs)}
            if route == "/articles/search":
                return 200, {"articles": self.archive, "has_more": False}
            if route.endswith("/runs"):
                return 200, {"runs": [], "has_more": False}
            run_id = route.split("/")[2]
            job = next((r for r in self.runs if r["id"] == run_id), None)
            if route.endswith("/claim"):
                key = body["request_id"]
                if key not in self.claims:
                    self.claims[key] = {
                        "attempt_id": "attempt" + str(len(self.claims)),
                        "attempt_number": 1 + sum(c["reporter"]["id"] == job["reporter"]["id"] for c in self.claims.values()),
                        "ownership_token": body["ownership_token"],
                        "claim_expires_at": time.time() + 21600,
                        "acknowledgment_only": job["reporter"]["paused"],
                        "reporter": dict(job["reporter"], prompt=job["reporter"]["prompt"] + "\nClaim snapshot."),
                    }
                if self.lose_claim_responses:
                    self.lose_claim_responses -= 1
                    return 503, {"error": "lost_response"}
                return 200, self.claims[key]
            if route.endswith("/renew"):
                return 200, {"attempt_id": body["attempt_id"], "claim_expires_at": time.time() + 21600}
            if route.endswith("/result"):
                self.results.append(deepcopy(body))
                if body["submission_id"] not in self.receipts:
                    if job:
                        attempts = sum(c["reporter"]["id"] == job["reporter"]["id"] for c in self.claims.values())
                        if body["outcome"] != "failed" or not body["error"]["retryable"] or attempts >= 3:
                            self.runs.remove(job)
                    self.receipts[body["submission_id"]] = {"run_id": run_id, "submission_id": body["submission_id"],
                             "outcome": body["outcome"], "article_ids": ["new"] if body["articles"] else []}
                if self.lose_result_responses:
                    self.lose_result_responses -= 1
                    return 503, {"error": "lost_response"}
                return 200, self.receipts[body["submission_id"]]
            raise AssertionError((method, path))


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.server = Newsroom()
        fixture = self.server

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.dispatch()

            def do_POST(self):
                self.dispatch()

            def dispatch(self):
                if (self.headers.get("CF-Access-Client-Id") != "test-id" or
                        self.headers.get("CF-Access-Client-Secret") != "test-secret"):
                    self.send_error(403)
                    return
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))) if self.command == "POST" else None
                status, payload = fixture.respond(self.command, self.path, body)
                if fixture.truncated_responses.get(self.path, 0):
                    fixture.truncated_responses[self.path] -= 1
                    self.send_response(status)
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    self.wfile.write(b'20\r\n{"incomplete":')
                    self.close_connection = True
                    return
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        class FixtureHTTPServer(ThreadingHTTPServer):
            request_queue_size = 32

        self.http = FixtureHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.fake = self.root / "codex"
        self.fake.write_text(f"#!{sys.executable}\n" + '''
import fcntl, json, os, pathlib, signal, subprocess, sys, time, urllib.request
root = pathlib.Path(__file__).parent
if "--version" in sys.argv:
    print("codex-cli 0.157.1")
    sys.exit(0)
if "login" in sys.argv:
    if json.loads((root / "fake.json").read_text()).get("login_failure"):
        sys.exit(1)
    print("Logged in using ChatGPT")
    sys.exit(0)
config = json.loads((root / "fake.json").read_text())
prompt = sys.stdin.read()
endpoint = json.loads(next(arg.split("=",1)[1] for arg in sys.argv if arg.startswith("mcp_servers.news_history.url=")))
def tool(name, arguments):
    body = json.dumps({"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{"name":name,"arguments":arguments}}).encode()
    req = urllib.request.Request(endpoint, data=body, headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)["result"]
found = tool("query", {"query":"related prior coverage", "limit":5})
matches = found["structuredContent"]["results"]
article = tool("get", {"file":matches[0]["file"], "maxLines":80}) if matches else None
(root / ("capture-" + str(os.getpid()) + ".json")).write_text(json.dumps({"prompt": prompt, "argv": sys.argv, "env": dict(os.environ), "cwd": os.getcwd(), "search":found,"article":article}))
if config.get("kill_supervisor"):
    while not (root / "supervisor.pid").exists():
        time.sleep(.01)
    os.kill(int((root / "supervisor.pid").read_text()), signal.SIGKILL)
    sys.exit(0)
if config.get("descendant"):
    descendant = subprocess.Popen([sys.executable, "-c", "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"])
    (root / "research-pids.tmp").write_text(json.dumps([os.getpid(), descendant.pid]))
    (root / "research-pids.tmp").replace(root / "research-pids.json")
with (root / "counts.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    state = json.loads((root / "counts.json").read_text()) if (root / "counts.json").exists() else {"active": 0, "peak": 0}
    state["active"] += 1
    state["peak"] = max(state["peak"], state["active"])
    (root / "counts.json").write_text(json.dumps(state))
deadline = time.monotonic() + 5
while True:
    with (root / "counts.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        peak = json.loads((root / "counts.json").read_text())["peak"]
    if peak >= config.get("wait_for_peak", 0):
        break
    if time.monotonic() > deadline:
        sys.exit(2)
    time.sleep(.01)
time.sleep(config.get("delay", 0))
with (root / "counts.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    state = json.loads((root / "counts.json").read_text())
    state["active"] -= 1
    (root / "counts.json").write_text(json.dumps(state))
if config.get("exit", 0):
    print("Authentication or allowance unavailable", file=sys.stderr)
    sys.exit(config["exit"])
output = pathlib.Path(sys.argv[sys.argv.index("--output-last-message") + 1])
output.write_text(config.get("raw", json.dumps(config["result"])))
print(json.dumps({"type": "turn.completed", "usage": {}}))
''')
        self.fake.chmod(0o700)
        self.fake_config = {"result": RESULT}
        self.settings = {
            "server_url": f"http://127.0.0.1:{self.http.server_port}",
            "client_id": "test-id", "client_secret": "test-secret",
            "state_dir": str(self.root / "state"), "codex": str(self.fake),
            "qmd_command": fake_qmd(self.root),
            "http_retry_delays": [0], "retry_delay_seconds": 0,
        }

    def execute(self):
        (self.root / "fake.json").write_text(json.dumps(self.fake_config))
        return run(self.settings)

    def captures(self):
        return [json.loads(p.read_text()) for p in self.root.glob("capture-*.json")]

    def test_claimed_instructions_and_dates_reach_codex_and_articles_reach_server(self):
        reporter = self.server.add()
        self.assertEqual(self.execute(), 0)
        capture, = self.captures()
        assignment = json.loads(capture["prompt"].split("Assignment JSON:\n", 1)[1])
        self.assertEqual(assignment["reporter"]["prompt"], reporter["prompt"] + "\nClaim snapshot.")
        self.assertEqual(assignment["expected_date"], "2026-09-27")
        self.assertEqual(assignment["reporting_date"], "2026-09-27")
        self.assertEqual(assignment["recent_articles"][0]["summary"], ARTICLE["summary"])
        delivered, = self.server.results
        self.assertEqual(delivered["articles"], [ARTICLE])
        self.assertEqual(delivered["outcome"], "published")
        claim, = self.server.claims.values()
        self.assertEqual(delivered["attempt_id"], claim["attempt_id"])
        self.assertEqual(delivered["ownership_token"], claim["ownership_token"])
        self.assertNotIn("test-secret", json.dumps(capture))
        self.assertIn("gpt-6-luna", capture["argv"])
        self.assertIn("--ignore-user-config", capture["argv"])
        self.assertIn('default_permissions="news_research"', capture["argv"])
        self.assertIn('permissions.news_research.filesystem={":minimal"="read",":workspace_roots"="read"}', capture["argv"])
        self.assertIn("permissions.news_research.network.enabled=false", capture["argv"])
        self.assertIn('mcp_servers.news_history.enabled_tools=["query", "get"]', capture["argv"])
        self.assertIn("Search the News history", capture["prompt"])
        self.assertNotIn("archive.jsonl", capture["prompt"])
        self.assertIn("id: old", capture["article"]["content"][0]["resource"]["text"])
        self.assertIn("https://example.com/story", capture["article"]["content"][0]["resource"]["text"])

    def test_paused_job_is_acknowledged_without_codex(self):
        self.server.add(paused=True)
        self.assertEqual(self.execute(), 0)
        self.assertEqual(self.captures(), [])
        self.assertEqual(self.server.results[0]["outcome"], "skipped_paused")

    def test_empty_day_still_checks_in_without_codex(self):
        self.assertEqual(self.execute(), 0)
        self.assertEqual(self.captures(), [])
        self.assertTrue(any(path.endswith("/check-ins") for _, path, _ in self.server.requests))

    def test_parallel_pool_runs_eight_jobs_and_keeps_context_separate(self):
        for number in range(10):
            self.server.add(number)
        self.fake_config["delay"] = .05
        self.fake_config["wait_for_peak"] = 8
        self.assertEqual(self.execute(), 0)
        self.assertEqual(json.loads((self.root / "counts.json").read_text())["peak"], 8)
        self.assertEqual(len(self.server.results), 10)
        assignments = [json.loads(c["prompt"].split("Assignment JSON:\n", 1)[1]) for c in self.captures()]
        self.assertEqual({a["reporter"]["id"] for a in assignments}, {f"reporter{i}" for i in range(10)})
        self.assertEqual(len({c["cwd"] for c in self.captures()}), 10)
        downloads = [path for _, path, _ in self.server.requests if "/articles/search?" in path]
        self.assertEqual(len(downloads), 1)
        self.assertEqual(list((self.root / "state/attempts").rglob("archive.jsonl")), [])

    def test_lost_claim_response_reuses_saved_request_and_token_after_restart(self):
        self.server.add()
        self.server.lose_claim_responses = 1
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.captures(), [])
        self.assertEqual(self.execute(), 0)
        requests = [body for _, path, body in self.server.requests if path.endswith("/claim")]
        self.assertEqual(requests[0], requests[1])
        self.assertEqual(len(self.server.claims), 1)

    def test_lost_result_receipt_recovers_before_discovery_without_new_research(self):
        self.server.add()
        self.server.lose_result_responses = 1
        self.assertEqual(self.execute(), 1)
        pending = list((self.root / "state/pending").glob("*.json"))
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].stat().st_mode & 0o777, 0o600)
        self.server.requests.clear()
        self.assertEqual(self.execute(), 0)
        self.assertTrue(self.server.requests[0][1].endswith("/result"))
        self.assertEqual(len(self.captures()), 1)
        self.assertEqual(self.server.results[0], self.server.results[1])
        self.assertEqual(len(self.server.receipts), 1)

    def test_invalid_json_does_not_publish_and_stops_at_three_attempts(self):
        self.server.add()
        self.fake_config["raw"] = "not JSON"
        self.execute()
        self.assertEqual(len(self.captures()), 3)
        self.assertEqual(len(self.server.results), 3)
        self.assertTrue(all(r["outcome"] == "failed" and r["articles"] == [] for r in self.server.results))

    def test_invalid_article_and_agent_process_failure_become_explicit_failures(self):
        for mode in ("invalid_article", "nonzero"):
            with self.subTest(mode=mode):
                self.server.add(len(self.server.claims))
                if mode == "invalid_article":
                    self.fake_config["result"] = deepcopy(RESULT)
                    self.fake_config["result"]["articles"][0]["sources"][0]["url"] = "javascript:alert(1)"
                else:
                    self.fake_config["exit"] = 1
                self.execute()
        self.assertEqual(len(self.server.results), 6)
        self.assertTrue(all(r["outcome"] == "failed" for r in self.server.results))

    def test_timeout_kills_codex_and_reports_failure(self):
        self.server.add()
        self.settings["attempt_timeout_seconds"] = .1
        self.fake_config["delay"] = 30
        started = time.monotonic()
        self.execute()
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(len(self.captures()), 3)
        self.assertTrue(all(r["error"]["code"] == "research_timeout" for r in self.server.results))
        for capture_path in self.root.glob("capture-*.json"):
            pid = int(capture_path.stem.split("-")[1])
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_nothing_to_publish_and_explicit_failure_are_forwarded(self):
        for outcome in ("nothing_to_publish", "failed"):
            self.server.add(len(self.server.claims))
            self.fake_config["result"] = {
                "outcome": outcome, "articles": [], "reason": "No useful new material.",
                "error": {"code": "source_unavailable", "message": "Cannot access required source.", "retryable": False} if outcome == "failed" else None,
            }
            self.execute()
        self.assertEqual([r["outcome"] for r in self.server.results], ["nothing_to_publish", "failed"])
        self.assertEqual(self.server.results[0]["reason"], "No useful new material.")
        self.assertFalse(self.server.results[1]["error"]["retryable"])

    def test_old_logs_expire_without_losing_an_unacknowledged_result(self):
        self.server.add()
        self.server.lose_result_responses = 1
        self.execute()
        for directory in (self.root / "state/attempts").iterdir():
            os.utime(directory, (0, 0))
        self.assertEqual(self.execute(), 0)
        self.assertEqual(len(self.captures()), 1)
        self.assertEqual(self.server.results[0], self.server.results[1])
        self.assertEqual(list((self.root / "state").rglob("prompt.txt")), [])

    def test_overlapping_start_does_not_claim_twice(self):
        self.server.add()
        self.fake_config["delay"] = .3
        (self.root / "fake.json").write_text(json.dumps(self.fake_config))
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(run, self.settings)
            deadline = time.monotonic() + 5
            while not self.captures() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(run(self.settings), 0)
            self.assertEqual(first.result(), 0)
        self.assertEqual(len(self.server.claims), 1)

    def test_api_authentication_failure_stops_before_claiming(self):
        self.server.add()
        self.server.failures["/check-ins"] = [1, 403]
        with self.assertRaisesRegex(Exception, "HTTP 403"):
            self.execute()
        self.assertEqual(self.server.claims, {})
        self.assertEqual(self.captures(), [])

    def test_crashed_research_gets_an_explicit_replacement_attempt(self):
        self.server.add()
        self.fake_config["kill_supervisor"] = True
        (self.root / "fake.json").write_text(json.dumps(self.fake_config))
        config = self.root / "worker.json"
        config.write_text(json.dumps(self.settings))
        config.chmod(0o600)
        crashed = subprocess.Popen(
            [sys.executable, "-B", "-m", "news.worker", "--config", str(config)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            (self.root / "supervisor.tmp").write_text(str(crashed.pid))
            (self.root / "supervisor.tmp").replace(self.root / "supervisor.pid")
            crashed.communicate(timeout=10)
        finally:
            if crashed.poll() is None:
                crashed.kill()
            crashed.communicate(timeout=5)
        self.assertEqual(crashed.returncode, -9)
        self.assertEqual(self.server.results, [])
        self.fake_config["kill_supervisor"] = False
        # Wait for the inherited process lock to close after research exits.
        deadline = time.monotonic() + 5
        with (self.root / "state/worker.lock").open("a") as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.01)
        self.assertEqual(self.execute(), 0)
        requests = [body for _, path, body in self.server.requests if path.endswith("/claim")]
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1]["replace_attempt_id"], "attempt0")
        self.assertNotEqual(requests[0]["ownership_token"], requests[1]["ownership_token"])
        self.assertEqual(len(self.server.results), 1)

    def test_orphaned_research_and_descendants_stop_before_restart(self):
        self.server.add()
        self.settings["attempt_timeout_seconds"] = 2
        self.fake_config.update(delay=30, descendant=True)
        (self.root / "fake.json").write_text(json.dumps(self.fake_config))
        config = self.root / "worker.json"
        config.write_text(json.dumps(self.settings))
        config.chmod(0o600)
        supervisor = subprocess.Popen(
            [sys.executable, "-B", "-m", "news.worker", "--config", str(config)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        pids = []
        try:
            ready = self.root / "research-pids.json"
            deadline = time.monotonic() + 5
            while not ready.exists():
                self.assertIsNone(supervisor.poll())
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.01)
            pids = json.loads(ready.read_text())
            supervisor.kill()
            supervisor.communicate(timeout=5)
            self.assertEqual(supervisor.returncode, -signal.SIGKILL)
            pending = self.root / "state/pending/run0.json"
            original = pending.read_bytes()
            request_count = len(self.server.requests)
            self.assertEqual(run(self.settings), 0)
            self.assertEqual(len(self.server.requests), request_count)
            self.assertEqual(len(self.server.claims), 1)

            def running(pid):
                state = subprocess.run(
                    ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True,
                ).stdout.strip()
                return bool(state) and not state.startswith("Z")

            deadline = time.monotonic() + self.settings["attempt_timeout_seconds"] + .5
            while any(running(pid) for pid in pids) and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertFalse(any(running(pid) for pid in pids), "Orphaned research outlived its deadline")
            with (self.root / "state/worker.lock").open("a") as lock:
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        self.assertLess(time.monotonic(), deadline, "The attempt did not release its lock")
                        time.sleep(.01)
            self.assertEqual(pending.read_bytes(), original)
            self.fake_config = {"result": RESULT}
            self.assertEqual(self.execute(), 0)
            requests = [body for _, path, body in self.server.requests if path.endswith("/claim")]
            self.assertEqual(len(requests), 2)
            self.assertEqual(requests[1]["replace_attempt_id"], "attempt0")
            self.assertEqual(len(self.server.results), 1)
        finally:
            if supervisor.poll() is None:
                supervisor.kill()
            supervisor.communicate(timeout=5)
            if pids:
                try:
                    os.killpg(pids[0], signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_http_retries_use_identical_claim_and_result_payloads(self):
        self.server.add()
        self.settings["http_retry_delays"] = [0, 0, 0]
        self.server.lose_claim_responses = 1
        self.server.lose_result_responses = 1
        self.assertEqual(self.execute(), 0)
        claims = [body for _, path, body in self.server.requests if path.endswith("/claim")]
        self.assertEqual(claims[0], claims[1])
        self.assertEqual(self.server.results[0], self.server.results[1])
        self.assertEqual(len(self.captures()), 1)

    def test_one_undeliverable_result_does_not_block_other_reporters(self):
        self.server.add(0)
        self.server.add(1)
        self.server.failures["/runs/run0/result"] = [20, 503]
        self.assertEqual(self.execute(), 1)
        self.assertEqual(len(self.captures()), 2)
        self.assertEqual(len(self.server.receipts), 1)
        self.assertEqual(self.server.results[0]["articles"], [ARTICLE])
        self.assertEqual(len(list((self.root / "state/pending").glob("*.json"))), 1)

    def test_truncated_claim_and_result_responses_retry_identical_payloads(self):
        self.server.add()
        self.settings["http_retry_delays"] = [0, 0, 0]
        self.server.truncated_responses = {
            "/api/v1/worker/runs/run0/claim": 1,
            "/api/v1/worker/runs/run0/result": 1,
        }
        self.assertEqual(self.execute(), 0)
        claims = [body for _, path, body in self.server.requests if path.endswith("/claim")]
        self.assertEqual(len(claims), 2)
        self.assertEqual(claims[0], claims[1])
        self.assertEqual(len(self.server.results), 2)
        self.assertEqual(self.server.results[0], self.server.results[1])
        self.assertEqual(len(self.server.receipts), 1)
        self.assertEqual(len(self.captures()), 1)

    def test_truncated_result_remains_pending_while_other_reporters_progress(self):
        self.server.add(0)
        self.server.add(1)
        self.server.truncated_responses["/api/v1/worker/runs/run0/result"] = 2
        self.assertEqual(self.execute(), 1)
        self.server.add(2)
        self.assertEqual(self.execute(), 1)
        self.assertEqual(len(self.server.receipts), 3)
        self.assertEqual(len(self.captures()), 3)
        self.assertEqual(len(list((self.root / "state/pending").glob("*.json"))), 1)
        self.assertEqual(self.execute(), 0)
        self.assertEqual(len(self.captures()), 3)
        self.assertEqual(list((self.root / "state/pending").glob("*.json")), [])

    def test_invalid_archive_pages_become_explicit_research_failures(self):
        original = self.server.respond
        for page in ({"has_more": False}, {"articles": None, "has_more": False}, {"articles": [], "has_more": 0}):
            with self.subTest(page=page):
                number = len(self.server.claims)
                self.server.add(number)
                self.server.respond = lambda method, path, body: (200, page) if "/articles/search" in path else original(method, path, body)
                self.assertEqual(self.execute(), 1)
                results = [body for _, path, body in self.server.requests if path == f"/api/v1/worker/runs/run{number}/result"]
                self.assertEqual(len(results), 3)
                self.assertTrue(all(body["outcome"] == "failed" for body in results))
        self.assertEqual(self.captures(), [])

    def test_damaged_pending_record_does_not_block_saved_results_or_discovery(self):
        self.server.add(0)
        self.server.lose_result_responses = 1
        self.assertEqual(self.execute(), 1)
        damaged = self.root / "state/pending/damaged.json"
        damaged.write_text("not JSON")
        self.server.add(1)
        self.assertEqual(self.execute(), 1)
        self.assertEqual(len(self.server.receipts), 2)
        self.assertEqual(len(self.captures()), 2)
        self.assertEqual(damaged.read_text(), "not JSON")
        self.assertEqual(list(damaged.parent.glob("*.json")), [damaged])

    def test_one_local_write_failure_does_not_skip_other_runs_retry_rounds(self):
        import io
        self.server.add(0)
        self.server.add(1)
        self.fake_config["result"] = {
            "outcome": "failed", "articles": [], "reason": "",
            "error": {"code": "source_unavailable", "message": "Try again.", "retryable": True},
        }
        replace = os.replace
        def replace_file(source, destination):
            if Path(destination).name == "run0.json":
                raise OSError("private-state-sentinel")
            return replace(source, destination)
        errors = io.StringIO()
        with patch("os.replace", side_effect=replace_file), patch("sys.stderr", errors):
            self.assertEqual(self.execute(), 1)
        self.assertEqual(len(self.server.results), 3)
        self.assertTrue(all(path.endswith("/runs/run1/result") for _, path, _ in self.server.requests if path.endswith("/result")))
        self.assertNotIn("private-state-sentinel", errors.getvalue())

    def test_agent_environment_excludes_api_keys_and_worker_credentials(self):
        from unittest.mock import patch
        self.server.add()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "paid-key-fixture", "CODEX_API_KEY": "paid-codex-key-fixture", "CF_ACCESS_CLIENT_SECRET": "service-secret-fixture"}):
            self.assertEqual(self.execute(), 0)
        captured = json.dumps(self.captures())
        captured += (self.root / "qmd-calls.jsonl").read_text()
        for secret in ("paid-key-fixture", "paid-codex-key-fixture", "service-secret-fixture", "test-secret"):
            self.assertNotIn(secret, captured)
        for path in (self.root / "state/attempts").rglob("*"):
            if path.is_file():
                self.assertNotIn("test-secret", path.read_text())

    def test_archive_download_follows_all_pages_and_supplies_recent_summaries(self):
        self.server.add()
        original = self.server.respond
        older = dict(ARTICLE, id="older", reporter_id="another-reporter")
        def respond(method, path, body):
            if "/articles/search" in path:
                self.server.requests.append((method, path, body))
                if "page=1" in path:
                    return 200, {"articles": self.server.archive, "has_more": True}
                return 200, {"articles": [older], "has_more": False}
            return original(method, path, body)
        self.server.respond = respond
        self.assertEqual(self.execute(), 0)
        archive = self.root / "state/history/articles"
        self.assertEqual({p.stem for p in archive.glob("*.md")}, {"old", "older"})
        self.assertTrue(any("page=2" in path for _, path, _ in self.server.requests))

    def test_expired_codex_login_reports_failure_but_still_acknowledges_paused_work(self):
        self.server.add(0)
        self.server.add(1, paused=True)
        self.fake_config["login_failure"] = True
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.captures(), [])
        outcomes = [r["outcome"] for r in self.server.results]
        self.assertEqual(outcomes.count("skipped_paused"), 1)
        self.assertEqual(outcomes.count("failed"), 3)

    def test_history_preparation_claims_no_work_and_calls_no_reporter(self):
        self.server.add()
        config = self.root / "worker.json"
        config.write_text(json.dumps(self.settings))
        config.chmod(0o600)
        result = subprocess.run([sys.executable, "-B", "-m", "news.worker", "--config", str(config), "--prepare-history"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 articles. No jobs claimed", result.stdout)
        self.assertEqual(self.captures(), [])
        self.assertEqual(self.server.claims, {})
        self.assertTrue(all("/articles/search" in path for _, path, _ in self.server.requests))

    def test_broken_history_is_an_explicit_failure_and_paused_work_still_finishes(self):
        self.server.add(0)
        self.server.add(1, paused=True)
        (self.root / "qmd-settings.json").write_text(json.dumps({"fail": "embed"}))
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.captures(), [])
        outcomes = [r["outcome"] for r in self.server.results]
        self.assertEqual(outcomes.count("skipped_paused"), 1)
        self.assertEqual(outcomes.count("failed"), 3)
