"""The real worker process stops cleanly on SIGTERM (1.1a carry-over).

Docker stops a container with SIGTERM, so this is the path that matters in production. It is
skipped on native Windows, where a process cannot be sent SIGTERM; CI runs it on Linux.
"""

import os
import signal
import subprocess
import sys
import threading
import time

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM cannot be sent on Windows"),
]


def test_sigterm_stops_an_idle_worker_with_exit_code_zero(test_db_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": test_db_url, "LLM_PROVIDER": "fake"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "ats.worker"],
        env=env,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stderr is not None
    lines: list[str] = []
    started = threading.Event()

    def read() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            lines.append(line)
            if "worker starting" in line:
                started.set()

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        assert started.wait(timeout=30), "the worker did not start:\n" + "".join(lines)
        time.sleep(0.5)  # let it enter the polling loop
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=15) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    reader.join(timeout=5)
    log = "".join(lines)
    assert "received signal" in log and "worker stopped" in log
