#!/usr/bin/env python3
"""Sanitize inherited protocol keys and disable legacy administration for tests.

This is byte-preserving outside the targeted definitions. It deliberately never
prints old values and must not be used to configure a production game server.
"""
from pathlib import Path
import re
import sys

source = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("src")
if len(sys.argv) > 2:
    raise SystemExit("Usage: sanitize-test-inputs.py [source-directory]")
path = source / "gmsv/include/version.h"
original = path.read_bytes()
pattern = re.compile(
    rb'^(?P<comment>\s*//\s*)?#define\s+'
    rb'(?P<name>_DEFAULT_PKEY|_RUNNING_KEY)\s+"[^"\r\n]*"[^\r\n]*(?:\r?\n|$)',
    re.MULTILINE,
)
seen = {b"_DEFAULT_PKEY": 0, b"_RUNNING_KEY": 0}
commented = 0

def replace(match):
    global commented
    if match.group("comment"):
        commented += 1
        return b""
    name = match.group("name")
    seen[name] += 1
    return b'#define ' + name + b' "BASELINE" /* Public test-only protocol marker. */\n'

updated = pattern.sub(replace, original)
if any(count != 1 for count in seen.values()) or commented not in (0, 4):
    raise SystemExit("Unexpected protocol definitions; refusing to write")
path.write_bytes(updated)
print("Client protocol definitions use public test-only markers.")

# This baseline never needs the legacy file-driven SIGUSR1 administration path.
main_path = source / "saac/main.c"
main = main_path.read_bytes()
main, handler_count = re.subn(
    rb"void sigusr1\(int a\)\s*\{.*?^\}",
    b"void sigusr1(int a)\n{\n    /* Disabled for isolated validation; no administrative file or shell action. */\n    (void)a;\n}",
    main, flags=re.MULTILINE | re.DOTALL,
)
if handler_count != 1:
    raise SystemExit("Unexpected administrative handler; refusing to write")

# Use only the configured service password; discard the legacy alternate suffix.
alt_pattern = re.compile(rb"#ifndef _VIP\n.*?#endif", re.DOTALL)
alternate = alt_pattern.findall(main)
if len(alternate) > 1 or (alternate and b"char buff" not in alternate[0]):
    raise SystemExit("Unexpected alternate password check; refusing to write")
main = alt_pattern.sub(b"    if (strcmp(svpas, svpass) == 0) {", main)

# Remove an already-disabled VIP check together with its commented old value.
main, dead_count = re.subn(
    rb"#ifdef _VIP\n[ \t]*if\(0\)//checkvip[^\n]*\n.*?#endif\n",
    b"", main, flags=re.DOTALL,
)
if dead_count > 1 or b"//checkvip" in main:
    raise SystemExit("Unexpected VIP check; refusing to write")
main_path.write_bytes(main)
print("Legacy administrative actions are disabled; service authentication uses configuration only.")

# Keep the alternate GMSV build consistent with configured-only SAAC authentication.
init_path = source / "gmsv/init.c"
init = init_path.read_bytes()
init, alt_count = re.subn(
    rb'#else\n[ \t]*char buff\[50\];\n[ \t]*sprintf\(buff,[^\n]+\n[ \t]*saacproto_ACServerLogin_send\(acfd, getGameservername\(\), buff\);\n#endif',
    b'#else\n        saacproto_ACServerLogin_send(acfd, getGameservername(), getAccountserverpasswd());\n#endif',
    init,
)
if alt_count > 1:
    raise SystemExit("Unexpected GMSV alternate authentication; refusing to write")
init_path.write_bytes(init)

# Distinct A/B names make (name != A || name != B) always true. Remove the
# inherited identifiers and avoid accessing Connect beyond its capacity here.
net_path = source / "gmsv/net.c"
net = net_path.read_bytes()
pattern = re.compile(
    rb'}else if \(strcmp\(Connect\[ sockfd \]\.cdkey, "(?P<a>[^"\n]+)"\)!=0 \|\| '
    rb'strcmp\(Connect\[ sockfd \]\.cdkey, "(?P<b>[^"\n]+)"\)!=0\) \{'
)
found = list(pattern.finditer(net))
if len(found) > 1 or any(m.group("a") == m.group("b") for m in found):
    raise SystemExit("Unexpected account exception; refusing to write")
net = pattern.sub(b'}else {', net)
net_path.write_bytes(net)
print("Alternate service authentication uses configuration; inherited account exception identifiers removed.")
