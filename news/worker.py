"""Daily reporting batches with durable API operations and bounded Claude Code attempts."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import fcntl
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
from zoneinfo import ZoneInfo

from . import validation as v
from .desktop_alerts import notify
from .errors import Problem
from .worker_claude import preflight, research
from .worker_history import History, preflight as history_preflight
from .worker_io import APIError, NewsAPI, WorkerError, read_json, remove_file, save_json

RETENTION_SECONDS = 7 * 24 * 3600


def failure(code, message):
    return {"outcome": "failed", "articles": [], "error": {
        "code": code, "message": message, "retryable": True,
    }}


class Batch:
    def __init__(self, settings, lock_fd):
        self.settings = settings
        self.api = NewsAPI(settings)
        self.root = Path(settings["state_dir"]).expanduser().resolve()
        self.pending = self.root / "pending"
        self.logs = self.root / "attempts"
        for directory in (self.pending, self.logs):
            directory.mkdir(mode=0o700, exist_ok=True)
        self.lock_fd = lock_fd
        self.errors = False
        self.failed_runs = set()
        self.claude_lock = threading.Lock()
        self.claude_checked = False
        self.claude_error = None
        self.history = History(settings, lock_fd)

    def check_claude(self):
        with self.claude_lock:
            if not self.claude_checked:
                self.claude_error = None
                try:
                    preflight(self.settings)
                except WorkerError as exc:
                    self.claude_error = exc
                self.claude_checked = True
            if self.claude_error:
                raise self.claude_error

    def cleanup(self):
        cutoff = time.time() - RETENTION_SECONDS
        for directory in self.logs.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            finished = directory / "finished.json"
            # Abandoned processes also have finite diagnostic retention. Pending
            # requests and complete results live separately and never expire here.
            stamp = read_json(finished)["at"] if finished.exists() else directory.stat().st_mtime
            if stamp < cutoff:
                shutil.rmtree(directory)

    def deliver(self, path, record):
        result = record["result"]
        receipt = self.api.call(f'/runs/{record["run"]["id"]}/result', result)
        if any(receipt.get(key) != value for key, value in {
            "run_id": record["run"]["id"], "submission_id": result["submission_id"],
            "outcome": result["outcome"],
        }.items()) or not isinstance(receipt.get("article_ids"), list):
            raise WorkerError("The server returned an inconsistent result receipt.")
        directory = self.logs / record["claim_request"]["request_id"]
        directory.mkdir(mode=0o700, exist_ok=True)
        save_json(directory / "finished.json", {"at": time.time(), "receipt": receipt})
        remove_file(path)
        print(f'Run {record["run"]["id"]}: {receipt["outcome"]}', flush=True)
        if result["outcome"] == "failed":
            self.failed_runs.add(record["run"]["id"])
            if receipt.get("run_state") == "failed" or not result["error"]["retryable"]:
                notify(self.settings, record=record)
        else:
            self.failed_runs.discard(record["run"]["id"])
        return result["outcome"] == "failed" and result["error"]["retryable"]

    def recover_results(self):
        retry = set()
        for path in self.pending.glob("*.json"):
            try:
                record = read_json(path)
                if "result" not in record:
                    continue
                if self.deliver(path, record):
                    retry.add(record["run"]["id"])
            except (WorkerError, Problem, OSError, ValueError, KeyError, TypeError) as exc:
                self.report_error(path.stem, exc)
        return retry

    def report_error(self, run_id, exc):
        self.errors = True
        message = str(exc) if isinstance(exc, (WorkerError, Problem)) else "Local state or API data is invalid or inaccessible; inspect private state."
        print(f"Run {run_id}: {message}", file=sys.stderr, flush=True)
        notify(self.settings, worker_failed=True)

    def discover(self):
        path = self.root / "checkin.json"
        request = {"request_id": secrets.token_hex(16)}
        save_json(path, request)
        return self.api.call("/check-ins", request)

    def process(self, job, reporting_date):
        run_id = v.identifier(job["id"], "run id")
        path = self.pending / f"{run_id}.json"
        if path.exists():
            record = read_json(path)
            if "result" in record:
                # Recovery already tried delivery; never replace saved research.
                return False
            claim = record.get("claim")
            if claim is None:
                claim = self.api.call(f"/runs/{run_id}/claim", record["claim_request"])
                record["claim"] = claim
                save_json(path, record)
            if record.get("research_started"):
                record = self.new_record(job, claim["attempt_id"])
                save_json(path, record)
        else:
            current = job.get("current_attempt")
            record = self.new_record(job, current["id"] if current else None)
            save_json(path, record)
        if "claim" not in record:
            record["claim"] = self.api.call(f"/runs/{run_id}/claim", record["claim_request"])
            save_json(path, record)
        claim = record["claim"]
        v.identifier(claim["attempt_id"], "attempt id")
        if claim["ownership_token"] != record["claim_request"]["ownership_token"]:
            raise WorkerError("The server returned an inconsistent claim token.")
        directory = self.logs / record["claim_request"]["request_id"]
        directory.mkdir(mode=0o700, exist_ok=True)
        if claim["acknowledgment_only"]:
            candidate = {"outcome": "skipped_paused", "articles": [], "reason": "Nothing to submit because the reporter is paused."}
        else:
            try:
                self.check_claude()
                reporter = claim["reporter"]
                reporter_id = v.identifier(reporter["id"], "reporter id")
                self.history.prepare(self.api)
                recent = self.history.summaries.get(reporter_id, [])
                history = self.api.call(f"/reporters/{reporter_id}/runs?limit=30")["runs"]
                assignment = {
                    "reporter": reporter, "run_id": run_id,
                    "expected_date": record["run"]["expected_date"], "run_kind": record["run"]["kind"],
                    "reporting_date": reporting_date,
                    "current_time": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
                    "recent_articles": recent, "recent_runs": history,
                    "history_snapshot": self.history.snapshot,
                }
                record["research_started"] = True
                save_json(path, record)
                candidate = research(self.settings, directory, assignment, self.lock_fd, self.history.endpoint)
                self.history.check()
            except subprocess.TimeoutExpired:
                candidate = failure("research_timeout", "Claude Code exceeded the reporting attempt time limit.")
            except (WorkerError, Problem, ValueError, UnicodeError) as exc:
                save_json(directory / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
                candidate = (failure("invalid_result", str(exc)) if isinstance(exc, Problem) else
                             failure("research_failed", "Research or result validation failed; inspect the private attempt log."))
        record["result"] = {
            "submission_id": secrets.token_hex(16), "attempt_id": claim["attempt_id"],
            "ownership_token": record["claim_request"]["ownership_token"], **candidate,
        }
        save_json(path, record)
        return self.deliver(path, record)

    def new_record(self, job, replacement=None):
        request = {"request_id": secrets.token_hex(16), "ownership_token": secrets.token_urlsafe(32)}
        if replacement:
            request["replace_attempt_id"] = v.identifier(replacement, "attempt id")
        return {"run": job, "claim_request": request}

    def execute(self):
        try:
            return self.execute_batch()
        finally:
            self.history.close()

    def execute_batch(self):
        self.cleanup()
        recovered_retries = self.recover_results()
        discovery = self.discover()
        jobs = discovery["runs"]
        allowed = {job["id"] for job in jobs} | recovered_retries
        for round_number in range(3):
            retry = set()
            self.claude_checked = False
            with ThreadPoolExecutor(max_workers=self.settings.get("concurrency", 8)) as pool:
                futures = {pool.submit(self.process, job, discovery["reporting_date"]): job["id"] for job in jobs}
                for future in as_completed(futures):
                    try:
                        if future.result():
                            retry.add(futures[future])
                    except (WorkerError, Problem, OSError, ValueError, KeyError, TypeError) as exc:
                        self.report_error(futures[future], exc)
            retry |= recovered_retries
            recovered_retries.clear()
            if not retry or round_number == 2:
                break
            # Daily discovery is bounded to the initial batch. Further requests
            # service its server-governed retry allowance, not new daily work.
            time.sleep(self.settings.get("retry_delay_seconds", 905))
            discovery = self.discover()
            jobs = [job for job in discovery["runs"] if job["id"] in retry & allowed]
        return 1 if self.errors or self.failed_runs else 0


def run(settings):
    settings = dict(settings)
    settings.setdefault("state_dir", str(Path.home() / ".local/state/news-worker"))
    settings.setdefault("claude", shutil.which("claude") or "claude")
    concurrency = settings.get("concurrency", 8)
    if type(concurrency) is not int or not 1 <= concurrency <= 8:
        raise WorkerError("concurrency must be between 1 and 8.")
    timeout = settings.get("attempt_timeout_seconds", 1800)
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 1800:
        raise WorkerError("attempt_timeout_seconds must be positive and at most 1800.")
    root = Path(settings["state_dir"]).expanduser().resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    with (root / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("News worker is already running; this start was skipped.", flush=True)
            return 0
        batch = Batch(settings, lock.fileno())
        result = batch.execute()
        notify(settings, worker_failed=batch.errors)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home() / ".config/news/worker.json")
    parser.add_argument("--check", action="store_true", help="Check Claude Code login and API access without claiming work or invoking a model.")
    parser.add_argument("--prepare-history", action="store_true", help="Refresh and verify local history search without claiming or publishing work.")
    args = parser.parse_args()
    settings = {}
    try:
        if args.config.stat().st_mode & 0o077:
            raise WorkerError("Worker config contains credentials: set its permissions to 0600.")
        settings = read_json(args.config)
        settings.setdefault("state_dir", str(Path.home() / ".local/state/news-worker"))
        if args.prepare_history:
            root = Path(settings["state_dir"]).expanduser().resolve()
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            with (root / "worker.lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise WorkerError("The worker is running. Prepare history when the batch has finished.") from None
                history = History(settings, lock.fileno())
                try:
                    history.prepare(NewsAPI(settings))
                    print(f'History search ready: {history.snapshot["article_count"]} articles. No jobs claimed.')
                finally:
                    history.close()
            return 0
        if args.check:
            settings.setdefault("claude", shutil.which("claude") or "claude")
            preflight(settings)
            history_preflight(settings)
            NewsAPI(settings).call("/articles/search?limit=1")
            print("Claude Code subscription login, QMD version, and News API access verified. No model was called.")
            return 0
        return run(settings)
    except (WorkerError, OSError, ValueError, KeyError, Problem) as exc:
        # Do not print config contents, credentials, or remote response bodies.
        print(str(exc) if isinstance(exc, WorkerError) else "Worker setup or local state is invalid; inspect the private configuration and state.", file=sys.stderr)
        if not args.check and not args.prepare_history:
            notify(settings, worker_failed=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
