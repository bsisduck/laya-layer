"""Own one service and stop it when the supervisor's pipe closes, even on SIGKILL."""

import json
import os
import select
import signal
import subprocess
import sys
from typing import Any


def main() -> None:
    descriptor = int(sys.argv[1])
    command = json.loads(sys.argv[2])
    stopping = False

    def request_stop(signum: int, frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, close_fds=True)
    try:
        while not stopping and child.poll() is None:
            readable, _, _ = select.select([descriptor], [], [], 0.1)
            if readable and os.read(descriptor, 1) == b"":
                stopping = True
    finally:
        os.close(descriptor)
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)
    # Give the supervisor a truthful child-exit signal even if service exited cleanly.
    raise SystemExit(child.returncode or 0)


if __name__ == "__main__":
    main()
