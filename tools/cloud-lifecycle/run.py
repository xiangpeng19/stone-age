#!/usr/bin/env python3
"""Run the lifecycle test with fresh fixtures and fail-closed network isolation."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys

from fixtures import ACCOUNT, PASSWORD

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

def inside(args):
    # unshare must have produced a different network namespace before any listener.
    if os.readlink('/proc/self/ns/net') == args.parent_net:
        raise SystemExit('Refusing to run without a new network namespace')
    # Inspect the current namespace, not a potentially inherited sysfs mount.
    interfaces = {line.split(':')[0].strip() for line in Path('/proc/net/dev').read_text().splitlines() if ':' in line}
    if interfaces != {'lo'}:
        raise SystemExit(f'Unexpected isolated network interfaces: {interfaces}')
    s = socket.socket()
    fcntl.ioctl(s, 0x8914, struct.pack('16sH14s', b'lo', 9, b''))
    s.close()
    cmd = ['bwrap', '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--die-with-parent',
           '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
           '--symlink', 'usr/lib64', '/lib64', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
           '--ro-bind', str(args.deps), '/deps', '--ro-bind', str(HERE), '/test',
           '--bind', str(args.output/'runtime'), '/run-test', '--bind', str(args.output/'logs'), '/logs',
           '--ro-bind', str(args.output/'schema.sql'), '/schema.sql', '--clearenv',
           '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', '/tmp',
           '--setenv', 'LD_LIBRARY_PATH', '/deps/usr/lib/x86_64-linux-gnu',
           '--chdir', '/run-test', '/bin/bash', '/test/inside.sh']
    os.execvp(cmd[0], cmd)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--deps', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--parent-net', help=argparse.SUPPRESS)
    args = p.parse_args()
    args.deps = args.deps.resolve()
    args.output = args.output.resolve()
    if args.inside:
        inside(args)
    if args.output.exists():
        raise SystemExit('Refusing to reuse existing output; choose a fresh directory')
    args.output.mkdir(parents=True)
    (args.output/'logs').mkdir()
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    provenance = {
        'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_diff_sha256': hashlib.sha256(subprocess.check_output(['git', 'diff', '--binary', '--', 'gmsv', 'saac'], cwd=ROOT)).hexdigest(),
        'compiler': subprocess.check_output(['gcc', '--version'], text=True).splitlines()[0],
        'executables': {name: sha(ROOT/name) for name in ('saac/saacjt.exe', 'gmsv/gmsvjt.exe')},
        'dependency_binaries': {name: sha(args.deps/name) for name in ('usr/sbin/mariadbd', 'usr/lib/x86_64-linux-gnu/libmariadb.so.3')},
        'test_files': {p.name: sha(p) for p in sorted(HERE.iterdir()) if p.suffix in ('.py', '.sh')},
        'build_command': 'DEPS_ROOT=<extracted packages> LOG_DIR=<build logs> bash tools/cloud-lifecycle/build.sh',
    }
    (args.output/'logs/provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    subprocess.run([sys.executable, str(ROOT/'tools/cloud-baseline/prepare-runtime.py'), '--output', str(args.output/'runtime')], cwd=ROOT, check=True)
    config = args.output/'runtime/gmsv/setup.cf'
    lines = config.read_text().splitlines()
    lines = [line for line in lines if not line.startswith('CharSaveinterval=')]
    config.write_text('\n'.join(lines)+'\nCharSaveinterval=1\n')
    schema = (ROOT/'tools/cloud-baseline/schema.sql').read_text()
    schema += f"\n-- Public disposable fixture, never a real account.\nINSERT INTO sa.user_table (Name,Pass,Path) VALUES ('{ACCOUNT.decode('ascii')}','{PASSWORD.decode('ascii')}','');\n"
    (args.output/'schema.sql').write_text(schema)
    command = ['timeout', '--signal=TERM', '--kill-after=10s', '150s', 'unshare', '-Urn', sys.executable, str(HERE/'run.py'), '--inside', '--deps', str(args.deps), '--output', str(args.output), '--parent-net', os.readlink('/proc/self/ns/net')]
    try:
        with (args.output/'logs/runtime-result.log').open('wb') as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
    finally:
        # bwrap's private PID namespace dies when the wrapper exits; no DB reused.
        database = args.output/'runtime/db'
        if database.exists():
            shutil.rmtree(database)
        if database.exists():
            raise RuntimeError('Disposable database cleanup did not complete')
        (args.output/'logs/cleanup.json').write_text(json.dumps({'database_removed': True, 'private_namespace_command_exited': True})+'\n')
    print((args.output/'logs/runtime-result.log').read_text(errors='replace'))
    print('Evidence:', args.output/'logs')
    raise SystemExit(result.returncode)

if __name__ == '__main__':
    main()
