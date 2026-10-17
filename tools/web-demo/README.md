# Private Stone Age browser demo

This is a single-fixture protocol demo: one map, one placeholder character,
native login/create/select, authoritative cardinal movement, confirmation of
the existing native autosave, disconnect/reconnect persistence, and normal
logout. No game assets are downloaded or copied from external sources.

Only the public `life_fixture` identity is used. The browser sends an `enter`
action; it does not accept accounts, passwords, native packets or backend
addresses. The codec is reused without the lifecycle client's packet logger.

## Boundary

```
Mac 127.0.0.1:18680 -- SSH -L --> Linux 127.0.0.1:18680
                               narrow byte relay
                                      |
                             private gateway Unix socket
                                      |
           new user/network/PID/IPC/UTS namespaces + bubblewrap filesystem
           gateway -> 127.0.0.1:19065 GMSV -> SAAC -> temporary MariaDB
```

The shared socket directory is private (0700), and its socket is 0600. The
gateway has no TCP listener. The host relay has one fixed Unix-socket target,
listens only on loopback, and never exposes the native server/database ports.
No firewall, SSH, AppArmor or sysctl changes are needed. There is no
non-isolated fallback. The old servers never execute directly in the host
root filesystem/network namespace.

Requests require exactly `Host: 127.0.0.1:18680`. WebSocket upgrades also require
exactly `Origin: http://127.0.0.1:18680`; arbitrary queries and cross-origin
handshakes are rejected. State changes only use that WebSocket. There are no
cookies, bearer tokens or persistent access credentials. CSP disallows frames,
external scripts and objects. Game strings are rendered with `textContent`.

One control session is allowed. A second tab gets `demo_busy`. There is no
pending action queue: while one request is executing another is rejected as
busy. Completed request IDs are cached (32 entries), movement is serialized and
paced, client frames are limited to 1024 bytes, and more than 12 messages per
second closes a session. Four WebSocket connections/eight relay peers are the
maximum. These are small demo limits, not a production security claim.

Map data uses the actual returned clipped bounds. Its base62 alphabet is
`0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ`, from
`gmsv/util.c:cnv10to62`, and differs from the wire codec. Empty object/event
tokens mean zero. Tile/object/event layers are checked against returned area.
The browser never predicts passability: blocked moves retain the server's
coordinates. The save button confirms real native autosave; it does not write
character records or invent a new save opcode.

## Run

Use the source-built SAAC/GMSV and private Jammy MariaDB/bubblewrap dependency
root from the lifecycle instructions. Privately extract Ubuntu's
`python3-aiohttp` and its dependencies into the same root. This implementation
supports the Ubuntu `3.8.1-4ubuntu0.2` aiohttp API. No system Python
installation or persistent service is required.

```sh
python3 tools/web-demo/run.py --deps /absolute/deps/root \
  --output /absolute/new-demo-run --port 18680 --duration 7200
```

The output must be new. The supervisor cleans the disposable database/runtime
and closes its host relay on stop/failure/expiry (at most two hours). While the
demo runs, its fixture state survives native/browser disconnects. Stop/reset
deliberately discards it; restart/crash durability is not claimed.

On the Mac, use existing SSH authentication and host trust:

```sh
ssh -N -T -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o ExitOnForwardFailure=yes -o ForwardAgent=no \
  -L 127.0.0.1:18680:127.0.0.1:18680 user@demo-linux-host
```

Open `http://127.0.0.1:18680`. Stop that tunnel with Ctrl-C. Stop the remote demo:

```sh
python3 tools/web-demo/stop.py --output /absolute/new-demo-run
```

The stop helper checks the recorded PID's start time and command before sending
a signal. It never broadly kills processes. Ports and output directories are
never replaced when already in use.

## Verify

`test_gateway.py` checks native map alphabet compatibility, bounds/empty layers,
fixed-input allowlists, HTTP Host/CSP and WebSocket Origin/invalid frames.
`verify_web.py --port 18680 --output /absolute/results.json` drives the actual
running gateway through entry, duplicate requests, second controller rejection,
rapid input, an interior blocked destination, native autosave, abrupt WS loss,
reconnect, explicit disconnect, normal logout, oversized frames and rate limits.
It stores only asserted public test facts.

The browser also needs a real manual/UI pass of entry, key movement, save,
reconnect and a second tab. Native lifecycle regression remains required.

Not implemented or validated: battle, pets, inventory/quests, a complete game
client, production auth/security, crash recovery or long-session stability.
The P1 reserved field retains an explicitly unverified historical meaning;
see `../cloud-lifecycle/STATUS-CONTRACT.md`.

Framework API reference: https://docs.aiohttp.org/en/v3.8.1/web_reference.html
