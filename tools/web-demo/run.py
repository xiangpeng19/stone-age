#!/usr/bin/env python3
"""Run one disposable web demo; expose only a loopback HTTP/WS relay."""
import argparse
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/"tools/cloud-lifecycle"))
from fixtures import ACCOUNT, PASSWORD


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2)+"\n")


def inside(args):
    namespace = os.readlink("/proc/self/ns/net")
    if namespace == args.parent_net:
        raise SystemExit("Refusing shared host network namespace")
    interfaces = {line.split(":")[0].strip() for line in Path("/proc/net/dev").read_text().splitlines() if ":" in line}
    if interfaces != {"lo"}:
        raise SystemExit("Refusing unexpected network interfaces")
    control = socket.socket()
    fcntl.ioctl(control, 0x8914, struct.pack("16sH14s", b"lo", 9, b""))
    control.close()
    write_json(args.output/"logs/namespace.json", {
        "different_from_host": True, "net": namespace, "interfaces": sorted(interfaces)})
    command = [str(args.deps/"usr/bin/bwrap"), "--unshare-pid", "--unshare-ipc", "--unshare-uts",
               "--die-with-parent", "--new-session", "--ro-bind", "/usr", "/usr",
               "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
               "--symlink", "usr/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
               "--ro-bind", str(args.deps), "/deps", "--ro-bind", str(HERE), "/web-demo",
               "--ro-bind", str(ROOT/"tools/cloud-lifecycle"), "/cloud-lifecycle",
               "--bind", str(args.output/"runtime"), "/run-test",
               "--bind", str(args.output/"logs"), "/logs",
               "--bind", str(args.output/"bridge"), "/bridge",
               "--ro-bind", str(args.output/"schema.sql"), "/schema.sql", "--clearenv",
               "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp",
               "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
               "--setenv", "PYTHONPATH", "/deps/usr/lib/python3/dist-packages",
               "--setenv", "LD_LIBRARY_PATH", "/deps/usr/lib/x86_64-linux-gnu",
               "--setenv", "DEMO_PORT", str(args.port), "--chdir", "/run-test",
               "/bin/bash", "/web-demo/inside.sh"]
    os.execv(command[0], command)


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def main(args):
    args.deps, args.output = args.deps.resolve(), args.output.resolve()
    if args.inside:
        inside(args)
    if args.deps == Path("/") or not (args.deps/"usr/bin/bwrap").is_file():
        raise SystemExit("Use the private extracted dependency root")
    if args.output.exists():
        raise SystemExit("Refusing to reuse output directory")
    if not 1024 <= args.port <= 65535 or not 60 <= args.duration <= 7200:
        raise SystemExit("Invalid local port or duration")
    with socket.socket() as probe:
        # A stopped relay can leave TIME_WAIT sockets; an active listener still fails.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", args.port))
    args.output.mkdir(mode=0o700)
    for name in ("logs", "bridge"):
        (args.output/name).mkdir(mode=0o700)
    subprocess.run([sys.executable, str(ROOT/"tools/cloud-baseline/prepare-runtime.py"),
                    "--output", str(args.output/"runtime")], cwd=ROOT, check=True)
    config = args.output/"runtime/gmsv/setup.cf"
    lines = [line for line in config.read_text().splitlines() if not line.startswith("CharSaveinterval=")]
    config.write_text("\n".join(lines)+"\nCharSaveinterval=1\n")
    schema = (ROOT/"tools/cloud-baseline/schema.sql").read_text()
    schema += f"\nINSERT INTO sa.user_table (Name,Pass,Path) VALUES ('{ACCOUNT.decode()}','{PASSWORD.decode()}','');\n"
    (args.output/"schema.sql").write_text(schema)
    expires = time.time()+args.duration
    write_json(args.output/"supervisor.json", {
        "pid": os.getpid(), "start_ticks": Path(f"/proc/{os.getpid()}/stat").read_text().split()[21],
        "port": args.port, "expires_unix": expires, "output": str(args.output)})
    write_json(args.output/"logs/provenance.json", {
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT)).hexdigest(),
        "executables": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ("gmsv/gmsvjt.exe", "saac/saacjt.exe")},
        "web_files": {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in str(p)},
        "host_network_namespace": os.readlink("/proc/self/ns/net")})
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    namespace_process = relay_process = None
    handles = []
    outcome = "stopped"
    try:
        namespace_log = (args.output/"logs/namespace-run.log").open("wb")
        handles.append(namespace_log)
        command = ["unshare", "-Urn", sys.executable, str(HERE/"run.py"), "--inside",
                   "--deps", str(args.deps), "--output", str(args.output), "--port", str(args.port),
                   "--parent-net", os.readlink("/proc/self/ns/net")]
        namespace_process = subprocess.Popen(command, stdout=namespace_log, stderr=subprocess.STDOUT,
                                             stdin=subprocess.DEVNULL, start_new_session=True)
        socket_path = args.output/"bridge/gateway.sock"
        end = time.monotonic()+45
        while not socket_path.exists():
            if stopped.is_set() or namespace_process.poll() is not None or time.monotonic() >= end:
                raise RuntimeError("Isolated gateway did not become ready")
            stopped.wait(0.25)
        relay_log = (args.output/"logs/relay.log").open("wb")
        handles.append(relay_log)
        relay_process = subprocess.Popen([sys.executable, str(HERE/"relay.py"), "--socket", str(socket_path),
                                          "--port", str(args.port)], stdout=relay_log, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, start_new_session=True)
        health_deadline = time.monotonic()+10
        while True:
            try:
                connection = http.client.HTTPConnection("127.0.0.1", args.port, timeout=2)
                connection.request("GET", "/health")
                response = connection.getresponse()
                healthy = response.status == 200 and json.loads(response.read())["ready"] is True
                connection.close()
                if healthy:
                    break
            except (OSError, ValueError, http.client.HTTPException):
                pass
            if stopped.is_set() or relay_process.poll() is not None or time.monotonic() >= health_deadline:
                raise RuntimeError("Loopback gateway health check failed")
            stopped.wait(0.25)
        ready = {"ready": True, "host_address": f"127.0.0.1:{args.port}",
                 "gateway_transport": "private Unix socket", "expires_unix": expires,
                 "namespace_pid": namespace_process.pid, "relay_pid": relay_process.pid}
        write_json(args.output/"ready.json", ready)
        print(json.dumps(ready), flush=True)
        while not stopped.is_set() and time.time() < expires:
            if namespace_process.poll() is not None or relay_process.poll() is not None:
                raise RuntimeError("A scoped demo process exited")
            stopped.wait(0.5)
    except Exception:
        outcome = "failed"
        raise
    finally:
        stop_process(relay_process)
        stop_process(namespace_process)
        for handle in handles:
            handle.close()
        # This directory was created exclusively for this run.
        if (args.output/"runtime").exists():
            shutil.rmtree(args.output/"runtime")
        (args.output/"schema.sql").unlink(missing_ok=True)
        (args.output/"bridge/gateway.sock").unlink(missing_ok=True)
        write_json(args.output/"cleanup.json", {"outcome": outcome, "scoped_processes_stopped": True,
                   "database_and_runtime_removed": True, "host_relay_closed": True})
        (args.output/"ready.json").unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deps", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18680)
    parser.add_argument("--duration", type=int, default=7200)
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--parent-net", help=argparse.SUPPRESS)
    main(parser.parse_args())
