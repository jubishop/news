"""A mock HTTP newsroom and a fake Claude Code executable around the real worker supervisor."""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

from news.worker import run
from history_support import Archive, fake_qmd
from news.worker_io import APIError

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
        self.reopenable = []
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
            if route == "/retries":
                reopened, self.reopenable = self.reopenable, []
                self.runs.extend(reopened)
                return 200, {"runs": [{
                    "id": job["id"], "reporter_id": job["reporter"]["id"], "reporter_name": job["reporter"]["name"],
                    "expected_date": job["expected_date"], "retry_generation": 2,
                } for job in reopened]}
            if route == "/articles/search":
                return 200, {"articles": self.archive, "has_more": False}
            if route.startswith("/articles/"):
                try:
                    return 200, Archive(self.archive).call(path.removeprefix("/api/v1/worker"))
                except APIError as exc:
                    return exc.status, {"error": exc.code}
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


class WorkerFixture(unittest.TestCase):
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
        self.fake = self.root / "claude"
        self.fake.write_text(f"#!{sys.executable}\n" + '''
import fcntl, json, os, pathlib, re, signal, subprocess, sys, time, urllib.request
root = pathlib.Path(__file__).parent
if "--version" in sys.argv:
    print("2.1.296 (Claude Code)")
    sys.exit(0)
if sys.argv[1:3] == ["auth", "status"]:
    status = json.loads((root / "fake.json").read_text())
    logged_in = not status.get("login_failure")
    print(json.dumps({"loggedIn": logged_in, "authMethod": status.get("auth_method", "claude.ai") if logged_in else "none", "apiProvider": "firstParty"}))
    sys.exit(0 if logged_in else 1)
config = json.loads((root / "fake.json").read_text())
prompt = sys.stdin.read()
time.sleep(config.get("startup_delay", 0))
endpoint = json.loads(pathlib.Path(sys.argv[sys.argv.index("--mcp-config") + 1]).read_text())["mcpServers"]["news_history"]["url"]
print(json.dumps({"type": "system", "subtype": "init", "mcp_servers": [
    {"name": "news_history", "status": config.get("history_status", "connected")},
    {"name": "news_fetch", "status": config.get("fetch_status", "connected")}]}), flush=True)
def tool(name, arguments):
    body = json.dumps({"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{"name":name,"arguments":arguments}}).encode()
    req = urllib.request.Request(endpoint, data=body, headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)["result"]
found = tool("query", {"query":"related prior coverage", "limit":5})
matches = found["structuredContent"]["results"]
article = tool("get", {"file":matches[0]["file"], "maxLines":80}) if matches else None
(root / ("capture-" + str(os.getpid()) + ".json")).write_text(json.dumps({"prompt": prompt, "argv": sys.argv, "env": dict(os.environ), "cwd": os.getcwd(), "search":found,"article":article}))
if os.environ.get("ANTHROPIC_API_KEY") and "key_events" in config:
    # How a run billed to an API key ends when the API refuses the request.
    for event in config["key_events"]:
        print(json.dumps(event))
    sys.exit(config.get("key_exit", 1))
if config.get("claude_stores"):
    # Claude Code saves oversized tool results and MCP logs in directories named for the cwd.
    name = re.sub("[^a-zA-Z0-9]", "-", os.getcwd())
    config_dir = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
    for saved in (config_dir / "projects" / name / "session/tool-results",
                  pathlib.Path.home() / "Library/Caches/claude-cli-nodejs" / name / "mcp-logs-news-history"):
        saved.mkdir(parents=True)
        (saved / "saved.txt").write_text(prompt)
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
# Claude Code reports the schema-validated draft only on its final result event.
final = {"type": "result", "subtype": "success", "is_error": False, "result": config.get("raw", json.dumps(config["result"]))}
if "raw" not in config:
    final["structured_output"] = config["result"]
print(json.dumps(final))
''')
        self.fake.chmod(0o700)
        self.fake_config = {"result": RESULT}
        self.settings = {
            "server_url": f"http://127.0.0.1:{self.http.server_port}",
            "client_id": "test-id", "client_secret": "test-secret",
            "state_dir": str(self.root / "state"), "claude": str(self.fake),
            "qmd_command": fake_qmd(self.root),
            "http_retry_delays": [0], "retry_delay_seconds": 0,
            # No key unless a test writes this file; the checkout's own .env never applies.
            "env_file": str(self.root / ".env"),
        }

    def execute(self):
        (self.root / "fake.json").write_text(json.dumps(self.fake_config))
        return run(self.settings)

    def captures(self):
        return [json.loads(p.read_text()) for p in self.root.glob("capture-*.json")]
