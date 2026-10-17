# Isolated Linux baseline

This directory preserves a successful GCC 14 x86-64 source build and isolated
SAAC/GMSV startup test. It is a development baseline, not a playable server or
production deployment. See [REPORT.md](REPORT.md) for the observed result and
remaining limitations.

## Source changes saved in this branch

The eight source files in the repository are already patched. Changes include
pointer/address-width fixes, database initialization and lock-query corrections,
redacted password logging, initialized socket options, and intentionally restricted
loopback networking and account registration for this validation. External clients
cannot connect to this baseline as written. The unused `_BACK_DOOR` define was
disabled; this is not evidence that a working backdoor was removed.

The inherited `_DEFAULT_PKEY` and `_RUNNING_KEY` values were replaced with the
public string `BASELINE`, and commented old values were removed. These are
disposable test markers, not real credentials; they are not suitable for real
clients or production. The SAAC/GMSV fixture marker is separate.
The legacy file-driven SIGUSR1 administrative handler is a no-op in this baseline;
its shell/control paths and commented VIP check value were removed. Service
authentication uses only the configured password on both services, with no
legacy alternate suffix. An always-true connection-capacity condition was
simplified, removing inherited account-name exceptions and an out-of-bounds read.

Original GB18030 source encoding is preserved. Do not transcode
`validated-baseline.patch` or the legacy C sources to UTF-8.

## Reproduce the historical test

Run only in an authorized disposable Linux environment with the prerequisites in
[REPORT.md](REPORT.md). Never use a real or public database. The harness creates
an empty database, uses a separate user/network namespace, then private PID/IPC/UTS
namespaces with bubblewrap. It must fail closed if isolation is unavailable.

From this directory:

```sh
mkdir -p logs deps/root
git clone https://github.com/xiangpeng19/stone-age.git src
git -C src checkout --detach 0c58fb6683a49a178a8ad845a8c296c2cb83bd81
# Download the five exact packages in DEPENDENCIES.md into deps/.
sha256sum -c SHA256SUMS
for package in deps/*.deb; do dpkg-deb -x "$package" deps/root; done
ln -s mariadb deps/root/usr/include/mysql
bash validated-build.sh
(cd src && python3 ../prepare-runtime.py)
timeout --signal=TERM 45s unshare -Urn python3 run-isolated.py >logs/runtime-result.log 2>&1
python3 verify-results.py
```

The wrapper applies the saved patch to that separate pinned checkout exactly
once, then runs `sanitize-test-inputs.py` without printing old values.
Do not apply it to the root of this branch a second time. The fixture
marker `fixture-only` is public test data, not a real credential. After confirming
all test processes have exited, remove `src/baseline-runtime/db`.

[evidence/test-results.json](evidence/test-results.json) and
[evidence/toolchain.txt](evidence/toolchain.txt) summarize the final sanitized run and pinned toolchain.
Full logs, dependency packages, runtime databases and built executables are not
included in this commit. Running the harness creates fresh logs under `logs/`.

The final sanitized sources, saved build wrapper and runtime harness passed a
complete fresh-checkout rebuild and isolated startup test on 2026-10-17. Client login, character
creation, gameplay, persistence, long-running stability and full security remain
untested.
