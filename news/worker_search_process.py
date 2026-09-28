"""Keep a search subprocess alive only while its supervisor's pipe is open."""

import os
import select
import signal
import subprocess
import sys


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # A launcher can exit before its descendants. Always stop the whole group.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def main():
    def interrupted(signum, frame):
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, interrupted)
    process = subprocess.Popen(sys.argv[1:], stdin=subprocess.DEVNULL, start_new_session=True)
    try:
        while process.poll() is None:
            ready, _, _ = select.select([sys.stdin], [], [], .1)
            if ready and not os.read(sys.stdin.fileno(), 1024):
                return 0
        return process.returncode
    finally:
        stop(process)


if __name__ == "__main__":
    sys.exit(main())
