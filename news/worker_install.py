"""Install the current owner's 06:00 Pacific cron entry after merge."""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys

from .worker_io import WorkerError, read_json

MARKER = "# news-reporting-worker"


def install(config, checkout, *, apply=False):
    config, checkout = Path(config).expanduser().resolve(), Path(checkout).resolve()
    if config.stat().st_mode & 0o077:
        raise WorkerError("Set worker config permissions to 0600.")
    settings = read_json(config)
    python = checkout / ".venv/bin/python"
    if not python.is_file():
        raise WorkerError("Run bin/app-setup in the permanent checkout first.")
    state = Path(settings.get("state_dir", Path.home() / ".local/state/news-worker")).expanduser().resolve()
    for path in (config, checkout, state, python):
        if any(character in str(path) for character in ("\n", "\r", "%")):
            raise WorkerError("Cron paths cannot contain newlines or percent signs.")
    command = f"cd {shlex.quote(str(checkout))} && {shlex.quote(str(python))} -B -m news.worker --config {shlex.quote(str(config))}"
    # The daemon uses the system timezone; a TZ assignment in the command does
    # not change when macOS cron starts it.
    entry = f"0 6 * * * {command} > {shlex.quote(str(state / 'cron.log'))} 2>&1 {MARKER}"
    if not apply:
        return entry
    if not os.readlink("/etc/localtime").endswith("/America/Los_Angeles"):
        raise WorkerError("Set the Mac system timezone to Pacific (America/Los_Angeles).")
    codex = settings.get("codex", "")
    if not os.path.isabs(codex):
        raise WorkerError("Set an absolute Codex executable path for cron.")
    subprocess.run([str(python), "-B", "-m", "news.worker", "--config", str(config), "--check"], cwd=checkout, check=True)
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
    if existing.returncode and not (existing.returncode == 1 and "no crontab for" in existing.stderr.lower()):
        raise WorkerError("Could not read crontab; existing jobs were not changed.")
    original = existing.stdout if existing.returncode == 0 else ""
    lines = [line for line in original.splitlines() if not line.endswith(MARKER)]
    replacement = "\n".join([*lines, entry]) + "\n"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    state.chmod(0o700)
    if replacement != original:
        subprocess.run(["crontab", "-"], input=replacement, text=True, check=True)
    verified = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=True)
    if verified.stdout != replacement:
        raise WorkerError("Installed crontab did not match; inspect crontab -l.")
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home() / ".config/news/worker.json")
    parser.add_argument("--install", action="store_true", help="Apply the entry. Without this flag, print it for review.")
    args = parser.parse_args()
    try:
        print(install(args.config, Path(__file__).resolve().parent.parent, apply=args.install))
    except (WorkerError, OSError, ValueError, subprocess.SubprocessError):
        print("Cron setup failed. Check the configuration, Pacific system timezone, and crontab access.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
