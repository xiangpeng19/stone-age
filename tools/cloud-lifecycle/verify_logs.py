#!/usr/bin/env python3
"""Check generated fixture logs without printing a password or login packet."""
import json
from pathlib import Path

from fixtures import ACCOUNT, PASSWORD, WRONG_PASSWORD
from protocol import encode_packet

logs = Path("/logs")
needles = [PASSWORD, WRONG_PASSWORD]
for password in (PASSWORD, WRONG_PASSWORD):
    packet = encode_packet(71, [ACCOUNT, password])
    needles.extend((packet, packet.hex().encode("ascii")))
checked = 0
for directory in (logs, Path("/run-test/gmsv/log"), Path("/run-test/saac/log")):
  for path in directory.rglob("*"):
    if path.is_file():
        data = path.read_bytes()
        if any(needle in data for needle in needles):
            raise SystemExit("Fixture login material found in generated logs")
        checked += 1
result = {"status": "passed", "files_checked": checked,
          "plaintext_passwords_absent": True, "raw_login_packets_absent": True}
(logs / "password-log-check.json").write_text(json.dumps(result, indent=2) + "\n")
print("PASSWORD_LOG_CHECK_PASSED")
