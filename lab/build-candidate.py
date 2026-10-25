#!/usr/bin/env python3
"""Build only the local candidate, keeping the full public build log."""
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import time


def main():
    root = Path(__file__).resolve().parents[1]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    log_path = Path(tempfile.gettempdir()) / f"timemachine-samba-build-{stamp}.log"
    command = [
        "docker", "--context", "colima", "compose", "--progress", "plain",
        "-f", "lab/compose.yaml", "build", "candidate",
    ]
    print(f"Mac / Colima: full build log: {log_path}", flush=True)
    last_progress = 0.0
    with log_path.open("x") as log:
        with subprocess.Popen(
            command, cwd=root, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        ) as process:
            # Prevent idle sleep only while this local Docker build is alive.
            awake = None
            if sys.platform == "darwin" and shutil.which("caffeinate"):
                awake = subprocess.Popen(["caffeinate", "-i", "-w", str(process.pid)])
            for line in process.stdout:
                log.write(line)
                log.flush()
                now = time.monotonic()
                if ">>>" in line or "ERROR" in line or now - last_progress >= 20:
                    print(line.rstrip(), flush=True)
                    last_progress = now
            returncode = process.wait()
            if awake is not None:
                awake.wait()
    print(f"Build exit={returncode}; full log: {log_path}", flush=True)
    return returncode


if __name__ == "__main__":
    sys.exit(main())
