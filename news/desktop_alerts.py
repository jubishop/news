"""Best-effort local failure notifications, independent of server email."""

import fcntl
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

from . import validation as v
from .errors import Problem
from .worker_io import WorkerError, read_json, save_json


def notify(settings, *, record=None, worker_failed=None):
    """Notify final failures once; a healthy batch rearms local worker alerts."""
    executable = settings.get("terminal_notifier")
    if not executable:
        return
    try:
        if not isinstance(executable, str) or not Path(executable).is_absolute():
            raise WorkerError("terminal_notifier must be an absolute path.")
        root = Path(settings["state_dir"]).expanduser().resolve() / "alerts"
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        with (root / "delivery.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = root / "seen.json"
            state = read_json(path) if path.exists() else {"attempts": [], "worker_failed": False}
            if (not isinstance(state, dict) or not isinstance(state.get("attempts"), list)
                    or any(not isinstance(value, str) for value in state["attempts"])
                    or type(state.get("worker_failed")) is not bool):
                raise WorkerError("Invalid desktop notification state.")
            if worker_failed is False:
                state["worker_failed"] = False
                save_json(path, state)
                return
            origin = settings.get("server_url", "").rstrip("/")
            try:
                parsed = urlsplit(origin)
                valid_origin = (parsed.scheme == "https" and parsed.hostname and not
                                (parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment))
            except ValueError:
                valid_origin = False
            url = origin + "/newsroom" if valid_origin else None
            if record is not None:
                identity = v.identifier(record["result"]["attempt_id"], "attempt id")
                if identity in state["attempts"]:
                    return
                reporter = record["claim"]["reporter"]
                if url:
                    url += "/reporters/" + v.identifier(reporter["id"], "reporter id")
                title = "News · Reporter failed"
                message = (f'{reporter["name"]} · {record["run"]["expected_date"]}\n'
                           "Reporting failed after its final attempt. Open the newsroom for details.")
                state["attempts"].append(identity)
            else:
                if state["worker_failed"]:
                    return
                identity = "worker"
                title = "News · Worker failed"
                message = "The local reporting worker could not start or finish its work. Check its private logs."
                state["worker_failed"] = True
            # stdin avoids terminal-notifier interpreting message text as options.
            subprocess.run(
                [executable, "-title", title, "-group", "news-failure-" + identity,
                 "-sound", "default", *(["-open", url] if url else [])],
                input=message, text=True, capture_output=True, check=True, timeout=15,
            )
            save_json(path, state)
    except (WorkerError, Problem, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("Desktop notification failed; check News alert configuration and notification permissions.",
              file=sys.stderr, flush=True)
