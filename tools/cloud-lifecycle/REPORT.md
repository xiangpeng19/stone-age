# Player lifecycle validation report

Date: 2026-10-17 UTC
Source: `fix/cloud-linux-baseline`, commit
`31054a13c00c2694c9c03c7675b8a00d91446bb9`.
Environment: disposable Linux x86-64 cloud workspace; GCC 14; MariaDB packages
from the existing baseline. No local Codex, user computer, or real accounts used.

## Results

- SAAC and GMSV fresh source builds: passed.
- Python codec versus extracted native C functions: all five test groups passed.
- Complete isolated lifecycle: passed with a fresh database and new character.
- Incorrect fixture password: reply `no`; correct password: `ok`.
- Create: reply `successful`, then the new character appears in the list.
- Enter: server status `C1006|30|40|15|22`.
- Map request: floor 1006, bounds (14,21)–(17,24), 85 data bytes.
- Move: ordinary W command with direction `a`; server status
  `C1006|30|40|15|21`.
- Autosave: file contains `fl=1006`, `x=15`, `y=21` before disconnect.
- Reconnect: server returns the same position, level 1, gold 1,000,000, base image
  100000, and vital/strength/toughness/dexterity 3/4/6/7 respectively. These match both the
  original server status and saved values (base stats are stored times 100).
- Explicit logout: reply `successful` / `success`; saved position becomes
  (1006,15,22), matching the existing return-to-elder rule.
- Isolation: only `lo`, no route; listeners 127.0.0.1:13306, :19300, :19065 inside
  the private namespace. Database deleted after process shutdown.

The final harness uses real socket requests and validates server checksums.
It also reads the disposable character file as independent persistence evidence.
No direct character edits, privileged game commands, or gameplay source patches
were used to achieve the passing result.

## Implementation

New `tools/cloud-lifecycle` contains the codec, native cross-checks, build wrapper,
fixture runner, lifecycle client and evidence. The only change to the previous
baseline harness is an optional `--output` argument in `prepare-runtime.py`, so
fresh runs do not reuse any prior runtime. The existing default is unchanged.
All inherited C files retain their original bytes and encoding.

During development, one run stopped before services started because an optional
sysfs check was unavailable. Another correctly reached movement/autosave but the
test's saved-record parser failed to account for the name/options prefix. These
were harness bugs, corrected before the final passing runs. They did not require
server changes.

## Unresolved findings and scope

`gmsv/char/char.c:2043` builds the P1 player-status packet with 28 `%d` placeholders
but 27 integer arguments. GCC reports the missing argument; the extra field is
undefined. This remains unchanged because the intended legacy-client schema is
not established. Assertions validate known fields rather than treating that
undefined field as reliable. This is a concrete follow-up before client work.

The game still logs the public fixture password in its inherited client-login
handler. No real password was used. Do not generalize this test into production
credential handling without hardening.

No battle, browser front end, NPC-save dialogue, cold service restart, load test,
full security audit, or production-readiness claim is made. No push, merge, PR or
public deployment was performed by this test task.
