#!/usr/bin/env python3
"""Stop only the recorded demo supervisor, rejecting a recycled PID."""
import argparse
import json
import os
from pathlib import Path
import signal
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
state = json.loads((output/"supervisor.json").read_text())
pid = state["pid"]
stat = Path(f"/proc/{pid}/stat")
if not stat.exists():
    if (output/"cleanup.json").exists() and not (output/"runtime").exists():
        print("Supervisor already exited; cleanup exists and runtime is absent")
        raise SystemExit(0)
    raise SystemExit("Supervisor exited; cleanup not confirmed")
if stat.read_text().split()[21] != state["start_ticks"]:
    raise SystemExit("Refusing recycled PID")
command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
if str(output).encode() not in command or not any(part.endswith(b"/web-demo/run.py") for part in command):
    raise SystemExit("Refusing unexpected supervisor command")
os.kill(pid, signal.SIGTERM)
end = time.monotonic()+25
while time.monotonic() < end:
    if (output/"cleanup.json").exists():
        cleanup = json.loads((output/"cleanup.json").read_text())
        assert cleanup["database_and_runtime_removed"] and cleanup["host_relay_closed"]
        print("Scoped demo stopped; runtime/database removed and loopback relay closed")
        break
    time.sleep(0.25)
else:
    raise SystemExit("Stop requested; cleanup not yet confirmed")
