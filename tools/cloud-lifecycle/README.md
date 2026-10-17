# Isolated player lifecycle test

This is a source-built, real-protocol integration test for the Linux baseline at
commit `31054a13c00c2694c9c03c7675b8a00d91446bb9`. It uses SAAC and GMSV together,
a fresh MariaDB fixture, and a small Python client. It does not emulate server
responses and does not use a desktop, game client, or an external account.

## Verified behavior

The test checks:

1. Incorrect password is rejected; fixture login succeeds.
2. An initially empty account can create and list `LifeFixture`.
3. The character enters map 1006 at (15,22), and the server supplies map data.
4. An ordinary walk command moves the authoritative position to (15,21).
5. The normal autosave path writes those coordinates to the SAAC character file
   while the client is still connected.
6. After disconnect/reconnect, map coordinates, level, gold, and base stats match
   both the prior server response and the persisted record.
7. Explicit protocol logout reports `successful` / `success` and saves again.

Normal logout deliberately returns the character to its elder's saved spawn,
(15,22), in the inherited game logic. An unexpected network disconnect preserves
the last location, (15,21), in this test. These are separate assertions.

The runtime-only setting `CharSaveinterval=1` shortens the existing autosave
interval; the server still polls it on its ordinary roughly 11-second cadence.
No gameplay source code is modified by this test. Account `life_fixture`, password
`demo-pass`, and protocol marker `BASELINE` are PUBLIC disposable test
fixtures, not credentials for any real service.

## Run

Use an authorized disposable Linux environment with GCC, Python 3, `unshare`,
`bubblewrap`, and the exact extracted MariaDB packages documented in
[../cloud-baseline/DEPENDENCIES.md](../cloud-baseline/DEPENDENCIES.md).
Network namespace creation must be allowed. There is no non-isolated fallback.

From the repository root:

```sh
export DEPS_ROOT=/absolute/path/to/deps/root
export LOG_DIR=/absolute/path/to/fresh-build-logs
bash tools/cloud-lifecycle/build.sh
python3 tools/cloud-lifecycle/test_protocol.py
python3 tools/cloud-lifecycle/run.py \
  --deps "$DEPS_ROOT" \
  --output /absolute/path/to/a-new-test-run
```

The output directory must not exist. Both servers must first be built from the
current checkout. The runner copies only built executables and the baseline's
allowlisted static data, never existing characters, databases, or accounts.
It creates a new user/network namespace, verifies that it differs from its
parent and has only loopback, then uses private PID/IPC/UTS namespaces and a
restricted bubblewrap filesystem. The only listening addresses are loopback
within that private namespace. The fixture database disables authentication only
inside this sandbox. Do not reuse that configuration for a real server.

The wrapper terminates the test processes and removes its disposable database.
A timeout additionally tears down the private PID namespace. Runtime character
files, configs and logs contain only generated fixtures and are kept for debug.
Local run logs include raw/decoded wire packets and hashes of saved fixture records.
Raw wire captures are intentionally not committed because the legacy P1 packet
contains an undefined extra field; the structured evidence retains only asserted
fields and public fixtures.
No services are deployed, exposed, or kept running.

## Evidence and limits

See [evidence/lifecycle-results.json](evidence/lifecycle-results.json) and
[REPORT.md](REPORT.md). The codec is independently compared to the actual C
implementation: 2,020 integer cases, 212 string cases, 100 outer-message cases,
packet schemas and literal golden vectors.

This validates the minimal player lifecycle only. It does not validate battle,
quests, inventory changes, NPC save-point interaction, concurrency, restart/crash
recovery, the Windows client, a browser UI, production security, or stability over
long sessions. Legacy compiler warnings remain. In particular, the P1 status
formatter has an extra integer placeholder without an argument; the test checks
only the documented fields and records this unresolved compatibility issue.

Updated P1 layout and login-capacity/logging checks are documented in [STATUS-CONTRACT.md](STATUS-CONTRACT.md). The committed historical evidence predates these fixes; use a fresh run for current evidence.
