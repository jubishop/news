"""The worker's own API key: billing it first and falling back to the subscription login."""

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

from worker_support import WorkerFixture

KEY = "sk-ant-api03-fixture-key"


def api_error(text, status, error="unknown", **fields):
    """The events with which Claude Code ends a print run on an API error.

    The shape follows Claude Code 2.1.312 run with an invalid key on October 28, 2026.
    """
    return [
        {"type": "assistant", "message": {"model": "<synthetic>", "role": "assistant", "content": [{"type": "text", "text": text}]},
         "error": error, "is_api_error_message": True, "api_error_status": status, "api_error_origin": "first_party", **fields},
        {"type": "result", "subtype": "success", "is_error": True, "api_error_status": status,
         "api_error_origin": "first_party", "terminal_reason": "api_error", "result": text, **fields},
    ]


def api_message(status, kind, message):
    return f"API Error: {status} " + json.dumps({"type": "error", "error": {"type": kind, "message": message}})


# A rejected key or an exhausted balance reruns the attempt on the subscription login.
KEY_FAILURES = {
    "invalid key": ("key_rejected", api_error("Invalid API key · Fix external API key", 401, "authentication_failed")),
    "forbidden key": ("key_rejected", api_error(api_message(403, "permission_error", "Your API key does not have permission to use the specified resource."), 403)),
    "disabled organization": ("key_rejected", api_error(
        "Your ANTHROPIC_API_KEY belongs to a disabled organization · Unset the environment variable to use your subscription instead",
        400, "invalid_request", api_error="org_disabled_credential")),
    "low credit": ("credit_balance", api_error("Credit balance is too low", 400, "billing_error")),
    "low credit from the API": ("credit_balance", api_error(api_message(400, "invalid_request_error",
        "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."),
        400, "invalid_request")),
    "low credit result only": ("credit_balance", [{"type": "result", "subtype": "success", "is_error": True,
        "result": "Credit balance too low · Add funds: https://platform.claude.com/settings/billing"}]),
    "spend limit": ("usage_limit", api_error(api_message(400, "invalid_request_error",
        "You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC."),
        400, "invalid_request")),
}
# Every other failure on the key behaves as it does on the subscription.
OTHER_KEY_FAILURES = {
    "rate limit": api_error(api_message(429, "rate_limit_error", "This request would exceed the rate limit for your organization."), 429, "rate_limit"),
    "overloaded": api_error(api_message(529, "overloaded_error", "Overloaded"), 529, "overloaded"),
    "server error": api_error(api_message(500, "api_error", "Internal server error"), 500, "server_error"),
    "prompt too long": api_error("Prompt is too long", 400, "invalid_request"),
    "crash without events": [],
}


class APIKeyTests(WorkerFixture):
    def write_key(self, text=f"# The worker's own key.\nexport OTHER=value\nNEWS_ANTHROPIC_API_KEY='{KEY}'\n", mode=0o600):
        path = Path(self.settings["env_file"])
        path.write_text(text)
        path.chmod(mode)

    def keyed(self):
        return [capture for capture in self.captures() if "ANTHROPIC_API_KEY" in capture["env"]]

    def test_configured_api_key_reaches_only_claude_code(self):
        self.server.add()
        self.write_key()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "inherited-key-fixture"}):
            self.assertEqual(self.execute(), 0)
        capture, = self.captures()
        self.assertEqual(capture["env"]["ANTHROPIC_API_KEY"], KEY)
        self.assertEqual([r["outcome"] for r in self.server.results], ["published"])
        directory = Path(capture["cwd"])
        self.assertEqual(json.loads((directory / "invocation.json").read_text())["auth"], "api_key")
        self.assertFalse((directory / "fallback.json").exists())
        for path in [*(self.root / "state").rglob("*"), self.root / "qmd-calls.jsonl"]:
            if path.is_file():
                self.assertNotIn(KEY, path.read_text(errors="replace"), path)
        # Claude Code hands its environment to stdio MCP servers; the page browser never receives the key.
        probe = self.root / "probe"
        probe.mkdir()
        (probe / "sitecustomize.py").write_text(
            "import json, os, pathlib\n"
            "pathlib.Path(os.environ['PROBE_OUT']).write_text(json.dumps(sorted(k for k in os.environ if 'ANTHROPIC' in k)))\n")
        argv = capture["argv"]
        fetch = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())["mcpServers"]["news_fetch"]
        handshake = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
        started = subprocess.run([fetch["command"], *fetch["args"]], input=handshake, capture_output=True, text=True,
                                 env=capture["env"] | {"PYTHONPATH": str(probe), "PROBE_OUT": str(self.root / "fetch-env.json")},
                                 cwd=capture["cwd"], timeout=120)
        self.assertEqual(json.loads(started.stdout.splitlines()[0])["id"], 1, started.stderr)
        self.assertEqual(json.loads((self.root / "fetch-env.json").read_text()), [])

    def test_rejected_key_or_exhausted_balance_reruns_the_attempt_on_the_subscription(self):
        for number, (shape, (trigger, events)) in enumerate(KEY_FAILURES.items()):
            with self.subTest(shape=shape):
                for path in self.root.glob("capture-*.json"):
                    path.unlink()
                self.server.add(number)
                self.write_key()
                self.fake_config["key_events"] = events
                output = io.StringIO()
                with patch("sys.stdout", output):
                    self.assertEqual(self.execute(), 0)
                keyed, = self.keyed()
                fallback, = [c for c in self.captures() if "ANTHROPIC_API_KEY" not in c["env"]]
                self.assertEqual(keyed["cwd"], fallback["cwd"])
                self.assertEqual(keyed["prompt"], fallback["prompt"])
                self.assertEqual(self.server.results[-1]["outcome"], "published")
                self.assertEqual(len(self.server.claims), number + 1)
                directory = Path(fallback["cwd"])
                self.assertEqual(json.loads((directory / "fallback.json").read_text())["trigger"], trigger)
                kept = [json.loads(line) for line in (directory / "api-key-events.jsonl").read_text().splitlines()]
                self.assertEqual(kept[-len(events):], events)
                self.assertIn('"structured_output"', (directory / "events.jsonl").read_text())
                self.assertIn(f"Attempt {directory.name}:", output.getvalue())
                self.assertIn("rerunning it on the Claude subscription login", output.getvalue())
                self.assertIn(f"({trigger})", output.getvalue())
                self.assertNotIn(KEY, output.getvalue())

    def test_failed_subscription_rerun_fails_the_attempt(self):
        self.server.add()
        self.write_key()
        self.fake_config.update(key_events=KEY_FAILURES["low credit"][1], exit=1)
        self.assertEqual(self.execute(), 1)
        self.assertEqual(len(self.keyed()), 3)
        self.assertEqual(len(self.captures()), 6)
        self.assertEqual([r["error"]["code"] for r in self.server.results], ["research_failed"] * 3)

    def test_other_failures_on_the_api_key_behave_as_on_the_subscription(self):
        for number, (shape, events) in enumerate(OTHER_KEY_FAILURES.items()):
            with self.subTest(shape=shape):
                for path in self.root.glob("capture-*.json"):
                    path.unlink()
                self.server.add(number)
                self.write_key()
                self.fake_config["key_events"] = events
                before = len(self.server.results)
                self.assertEqual(self.execute(), 1)
                self.assertEqual(len(self.keyed()), 3)
                self.assertEqual(len(self.captures()), 3)
                self.assertEqual([r["error"]["code"] for r in self.server.results[before:]], ["research_failed"] * 3)
        self.assertEqual(list((self.root / "state/attempts").glob("*/fallback.json")), [])
        # A finished run that only mentions these errors is research, not a key failure.
        for path in self.root.glob("capture-*.json"):
            path.unlink()
        self.server.add(len(OTHER_KEY_FAILURES))
        message = "The agency's API said: Invalid API key; credit balance is too low; usage limits reached."
        self.fake_config = {"result": {"outcome": "failed", "articles": [], "reason": "",
                                       "error": {"code": "source_unavailable", "message": message, "retryable": False}}}
        self.execute()
        self.assertEqual(len(self.keyed()), 1)
        self.assertEqual(self.server.results[-1]["error"]["message"], message)
        self.assertEqual(list((self.root / "state/attempts").glob("*/fallback.json")), [])

    def test_key_file_must_be_private_and_hold_one_token(self):
        for number, (text, mode, problem) in enumerate((
            (f"NEWS_ANTHROPIC_API_KEY={KEY}\n", 0o644, "set its permissions to 0600"),
            ("NEWS_ANTHROPIC_API_KEY=sk-ant-api03 fixture\n", 0o600, "NEWS_ANTHROPIC_API_KEY"),
        )):
            with self.subTest(mode=oct(mode), text=text):
                self.server.add(2 * number)
                self.server.add(2 * number + 1, paused=True)
                self.write_key(text, mode)
                before = len(self.server.results)
                self.assertEqual(self.execute(), 1)
                self.assertEqual(self.captures(), [])
                outcomes = [r["outcome"] for r in self.server.results[before:]]
                self.assertEqual(sorted(outcomes), ["failed"] * 3 + ["skipped_paused"])
                failures = [json.loads(p.read_text())["message"] for p in (self.root / "state/attempts").glob("*/failure.json")]
                self.assertTrue(failures and all(problem in message for message in failures), failures)
                self.assertNotIn(KEY, json.dumps(failures))
                for path in (self.root / "state/attempts").glob("*/failure.json"):
                    path.unlink()
        # A blank key, or a readable .env without one, leaves research on the subscription.
        for number, (text, mode) in enumerate((("NEWS_ANTHROPIC_API_KEY=\n", 0o600), ("OTHER=value\n", 0o644)), start=4):
            with self.subTest(text=text):
                self.server.add(number)
                self.write_key(text, mode)
                self.assertEqual(self.execute(), 0)
        self.assertEqual(len(self.captures()), 2)
        self.assertEqual(self.keyed(), [])

    def test_check_reads_the_key_from_the_checkout_env_file(self):
        checkout = self.root / "checkout"
        shutil.copytree(Path(__file__).resolve().parents[2] / "news", checkout / "news",
                        ignore=shutil.ignore_patterns("__pycache__"))
        settings = {key: value for key, value in self.settings.items() if key != "env_file"}
        config = self.root / "worker.json"
        config.write_text(json.dumps(settings))
        config.chmod(0o600)
        (self.root / "fake.json").write_text(json.dumps(self.fake_config))

        def check():
            return subprocess.run([sys.executable, "-B", "-m", "news.worker", "--config", str(config), "--check"],
                                  cwd=checkout, capture_output=True, text=True, timeout=120)

        result = check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No API key is configured", result.stdout)
        env = checkout / ".env"
        env.write_text(f"NEWS_ANTHROPIC_API_KEY={KEY}\n")
        env.chmod(0o600)
        result = check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"NEWS_ANTHROPIC_API_KEY from {env.resolve()}", result.stdout)
        self.assertNotIn(KEY, result.stdout + result.stderr)
        env.chmod(0o644)
        result = check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("set its permissions to 0600", result.stderr)
        self.assertNotIn(KEY, result.stdout + result.stderr)
        self.assertEqual(self.server.claims, {})
        self.assertEqual(self.captures(), [])
