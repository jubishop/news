#!/usr/bin/env python3
"""Run reporter administration over SSH using the deployed News application."""

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.version_info[:2] != (3, 14):
        parser.error("News reporter administration requires Python 3.14.")
    parser.add_argument("--host", default="root@5.78.193.133")
    parser.add_argument("--release", default="/opt/news/current")
    parser.add_argument("--database", default="/var/lib/news/news.sqlite3")
    parser.add_argument("--backup-dir", default="/var/lib/news/reporter-backups")
    commands = parser.add_subparsers(dest="action", required=True)
    listing = commands.add_parser("list", help="List active reporters without instructions")
    listing.add_argument("--all", action="store_true", help="Include retired reporters")
    commands.add_parser("show", help="Read a reporter and its configuration version").add_argument("id")
    create = commands.add_parser("create", help="Create a reporter from a JSON object")
    create.add_argument("--data", required=True, help="JSON file, or - for stdin")
    for action in ("update", "pause", "resume", "delete"):
        command = commands.add_parser(action)
        command.add_argument("id")
        command.add_argument("--if-version", required=True, type=int,
                             help="config_version from the last show result")
        if action == "update":
            command.add_argument("--data", required=True, help="JSON patch file, or - for stdin")
    args = parser.parse_args()
    request = vars(args).copy()
    host = request.pop("host")
    data = request.pop("data", None)
    try:
        request["values"] = json.loads(
            sys.stdin.read() if data == "-" else Path(data).read_text()
        ) if data else {}
        if not isinstance(request["values"], dict):
            raise ValueError("Reporter data must be a JSON object.")
        source = Path(__file__).with_name("remote.py").read_text()
        remote = shlex.join([
            "runuser", "-u", "news", "--", args.release.rstrip("/") + "/.venv/bin/python",
            "-B", "-c", source,
        ])
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
             "-o", "ConnectTimeout=10", "--", host, remote],
            input=json.dumps(request), text=True, capture_output=True, timeout=90,
        )
        try:
            response = json.loads(result.stdout)
        except ValueError:
            response = None
        if result.returncode == 255 or not isinstance(response, dict):
            raise RuntimeError("SSH did not return a complete result. Inspect list/show before retrying a change.")
        print(json.dumps(response, indent=2))
        return 0 if result.returncode == 0 else 1
    except (subprocess.TimeoutExpired, RuntimeError) as error:
        message = ("SSH timed out. Inspect list/show before retrying a change."
                   if isinstance(error, subprocess.TimeoutExpired) else str(error))
        print(json.dumps({"error": "outcome_unknown", "message": message}))
        return 1
    except (OSError, ValueError) as error:
        print(json.dumps({"error": "invalid_request", "message": str(error), "committed": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
