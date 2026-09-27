"""Independent deadline and process-group cleanup for one research attempt."""

import os
import signal
import subprocess
import sys
import time


TIMEOUT_EXIT = 124


def supervise(deadline, lock_fd, command):
    cancelled = False

    def cancel(signum, frame):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    process = None
    try:
        if time.monotonic() >= deadline:
            return TIMEOUT_EXIT
        if cancelled:
            return 1
        process = subprocess.Popen(command, start_new_session=True, pass_fds=(lock_fd,))
        while not cancelled:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return TIMEOUT_EXIT
            try:
                return 0 if process.wait(timeout=min(.1, remaining)) == 0 else 1
            except subprocess.TimeoutExpired:
                pass
        return 1
    finally:
        if process is not None:
            # Keep the inherited batch lock until the whole research group is
            # stopped, including descendants left behind after a normal exit.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


if __name__ == "__main__":
    sys.exit(supervise(float(sys.argv[1]), int(sys.argv[2]), sys.argv[3:]))
