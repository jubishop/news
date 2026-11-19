"""Refuse to rebuild the installed worker's environment while a batch runs from it.

bin/setup-application runs this file by path, before it replaces .venv and so
before any dependency exists, which is why it imports only the standard
library. It exits nonzero when the installed LaunchAgent runs from the given
checkout and a batch holds the worker lock. It only probes the lock: holding
it through the rebuild would make a 06:00 start skip that day's batch.
"""

import fcntl
import json
import os
from pathlib import Path
import plistlib
import shlex
import sys

LABEL = "com.jubishop.news.worker"


def worker_lock(settings):
    """Return the lock a batch holds, from the worker's settings, as news.worker resolves it."""
    state = Path(settings.get("state_dir", Path.home() / ".local/state/news-worker")).expanduser().resolve()
    return state / "worker.lock"


def runs_from(job, checkout):
    directory = job.get("WorkingDirectory")
    try:
        return bool(directory) and os.path.samefile(directory, checkout)
    except FileNotFoundError:
        return False


def held(lock):
    try:
        handle = lock.open("rb")
    except FileNotFoundError:
        return False  # No batch has run with this state directory.
    with handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


def batch_running(checkout):
    """Return whether the installed worker runs from checkout and a batch holds its lock."""
    try:
        data = (Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist").read_bytes()
    except FileNotFoundError:
        return False
    job = plistlib.loads(data)
    if not runs_from(job, checkout):
        return False
    # news.worker_install writes the command; it always names the configuration.
    words = shlex.split(job["ProgramArguments"][-1])
    settings = json.loads(Path(words[words.index("--config") + 1]).read_text(encoding="utf-8"))
    return held(worker_lock(settings))


def main(argv):
    if len(argv) != 1:
        print("Usage: setup_guard.py <checkout>", file=sys.stderr)
        return 2
    checkout = Path(argv[0]).resolve()
    try:
        running = batch_running(checkout)
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        # Do not print the configuration, which holds credentials.
        print(f"Could not tell whether the News worker is running from {checkout}: its LaunchAgent "
              f"({LABEL}) or configuration is unreadable. Setup left .venv unchanged.", file=sys.stderr)
        return 1
    if running:
        print(f"News worker is running from {checkout}, so setup left .venv unchanged. "
              "Run setup again after the batch finishes.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
