"""Install the current owner's 06:00 Pacific LaunchAgent after merge."""

import argparse
import fcntl
import os
from pathlib import Path
import plistlib
import shlex
import subprocess
import sys
import tempfile

from .worker_io import WorkerError, read_json

LABEL = "com.jubishop.news.worker"
# The worker was scheduled by cron before launchd; installation removes that entry.
LEGACY_CRON_MARKER = "# news-reporting-worker"


def definition(config, checkout, state):
    python = checkout / ".venv/bin/python"
    command = f"exec {shlex.quote(str(python))} -B -m news.worker --config {shlex.quote(str(config))} > {shlex.quote(str(state / 'scheduled.log'))} 2>&1"
    # launchd uses the system timezone and starts a calendar job missed
    # during sleep after wake. Each start replaces the previous batch log.
    return plistlib.dumps({
        "Label": LABEL, "ProgramArguments": ["/bin/sh", "-c", command],
        "WorkingDirectory": str(checkout), "StartCalendarInterval": {"Hour": 6, "Minute": 0},
    })


def legacy_crontab():
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
    if existing.returncode and not (existing.returncode == 1 and "no crontab for" in existing.stderr.lower()):
        raise WorkerError("Could not read crontab; existing jobs were not changed.")
    return existing.stdout if existing.returncode == 0 else None


def remove_legacy_cron(original):
    lines = [line for line in original.splitlines() if not line.endswith(LEGACY_CRON_MARKER)]
    if len(lines) == len(original.splitlines()):
        return
    if lines:
        replacement = "\n".join(lines) + "\n"
        subprocess.run(["crontab", "-"], input=replacement, text=True, check=True)
    else:
        replacement = None
        subprocess.run(["crontab", "-r"], capture_output=True, check=True)
    if legacy_crontab() != replacement:
        raise WorkerError("Installed crontab did not match; inspect crontab -l.")


def load(path, content):
    target = f"gui/{os.getuid()}/{LABEL}"

    def loaded():
        return subprocess.run(["launchctl", "print", target], capture_output=True, check=False).returncode == 0

    if loaded():
        # The file is replaced only after the previous job unloads, so a
        # matching file means launchd loaded this definition.
        if path.is_file() and path.read_bytes() == content:
            return
        subprocess.run(["launchctl", "bootout", target], capture_output=True, check=False)
        if loaded():
            raise WorkerError("launchd did not unload the previous worker agent; inspect launchctl print " + target + ".")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".news-worker-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    result = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)], capture_output=True, text=True, check=False)
    if result.returncode or not loaded():
        raise WorkerError("launchd did not load the worker agent; inspect launchctl print " + target + ".")


def install(config, checkout, *, apply=False):
    config, checkout = Path(config).expanduser().resolve(), Path(checkout).resolve()
    if config.stat().st_mode & 0o077:
        raise WorkerError("Set worker config permissions to 0600.")
    settings = read_json(config)
    python = checkout / ".venv/bin/python"
    if not python.is_file():
        raise WorkerError("Run bin/app-setup in the permanent checkout first.")
    state = Path(settings.get("state_dir", Path.home() / ".local/state/news-worker")).expanduser().resolve()
    content = definition(config, checkout, state)
    if not apply:
        return content.decode()
    if not os.readlink("/etc/localtime").endswith("/America/Los_Angeles"):
        raise WorkerError("Set the Mac system timezone to Pacific (America/Los_Angeles).")
    if not os.path.isabs(settings.get("claude", "")):
        raise WorkerError("Set an absolute Claude Code executable path for launchd.")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    state.chmod(0o700)
    with (state / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise WorkerError("The worker is running. Install after the batch has finished.") from None
        subprocess.run([str(python), "-B", "-m", "news.worker", "--config", str(config), "--check"], cwd=checkout, check=True)
        original = legacy_crontab()
        # Remove cron first so two schedulers never start the worker together.
        if original is not None:
            remove_legacy_cron(original)
        load(Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist", content)
    return content.decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home() / ".config/news/worker.json")
    parser.add_argument("--install", action="store_true", help="Load the agent. Without this flag, print it for review.")
    args = parser.parse_args()
    try:
        print(install(args.config, Path(__file__).resolve().parent.parent, apply=args.install), end="")
    except (WorkerError, OSError, ValueError, subprocess.SubprocessError):
        print("Worker installation failed. Check the configuration, Pacific system timezone, crontab, and launchd access.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
