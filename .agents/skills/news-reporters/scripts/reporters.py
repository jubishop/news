#!/usr/bin/env python3
"""Administer News reporters on the VPS through the deployed application.

Each command runs over SSH as the news user and prints a JSON object. A change
first backs up the database, replacing the previous helper backup at
BACKUP_DIR/reporters-before-change.sqlite3, then commits in one transaction
and reads the reporter back. Its result has before, after, backup_path, and
verified.
"""

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

DETAILS = """\
reporter data:
  A JSON object in a file, or - for stdin. create needs name, prompt, and
  cadence, plus that cadence's field; update sends only the fields it changes.
    daily     no other field
    weekly    weekdays: list of mon, tue, wed, thu, fri, sat, sun
    monthly   day_of_month: 1 to 31; shorter months use their last day
    once      dates: distinct YYYY-MM-DD contractor dates
  A list replaces the saved one, so keep contractor dates already due. New
  schedules take effect tomorrow, Pacific Time, and new contractor dates must be
  after today. A reporter can't change between once and the recurring cadences.

errors:
  A failure exits 1 with an error code and message. stale_version: show the
  reporter again and reconcile. outcome_unknown: SSH lost the reply, so the
  change may have committed; check list and show before retrying. The helper
  never retries a change.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=DETAILS,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    if sys.version_info < (3, 14):
        parser.error("News reporter administration requires Python 3.14 or later.")
    parser.add_argument("--host", default="root@100.91.85.40", help="SSH destination (default: %(default)s)")
    parser.add_argument("--release", default="/opt/news/current",
                        help="deployed release directory (default: %(default)s)")
    parser.add_argument("--database", default="/var/lib/news/news.sqlite3", help="(default: %(default)s)")
    parser.add_argument("--backup-dir", default="/var/lib/news/reporter-backups", help="(default: %(default)s)")
    commands = parser.add_subparsers(dest="action", required=True)
    listing = commands.add_parser("list", help="List active reporters without instructions")
    listing.add_argument("--all", action="store_true", help="Include completed and deleted reporters")
    commands.add_parser("show", help="Read a reporter with its instructions and config_version").add_argument("id")
    create = commands.add_parser("create", help="Create a reporter")
    create.add_argument("--data", required=True, help="JSON file, or - for stdin")
    for action, summary in (("update", "Change a reporter's fields"), ("pause", "Pause a reporter"),
                            ("resume", "Resume a paused reporter"),
                            ("delete", "Retire a reporter, cancelling its unstarted work")):
        command = commands.add_parser(action, help=summary)
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
