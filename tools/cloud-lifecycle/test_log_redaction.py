#!/usr/bin/env python3
"""Execute the actual ordinary/debug/registration log statements with a canary."""
from pathlib import Path
import json
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
calls = []
for relative, marker in (
    ("gmsv/callfromcli.c", b"Client login fd="),
    ("gmsv/lssproto_serv.c", b"LSSPROTO_CLIENTLOGIN_RECV password="),
    ("gmsv/lssproto_serv.c", b"LSSPROTO_SHUTDOWN_RECV password="),
    ("saac/sasql.c", b"register_sql="),
):
    lines = (ROOT / relative).read_bytes().splitlines()
    selected = [line.strip() for line in lines if marker in line]
    assert len(selected) == 1
    call = selected[0].decode("ascii")
    assert "[redacted]" in call
    calls.append(call)

with tempfile.TemporaryDirectory(prefix="stoneage-redaction-") as directory:
    directory = Path(directory)
    c_file, binary = directory / "logs.c", directory / "logs"
    c_file.write_text(
        '#include <stdio.h>\n#define print printf\n'
        'int main(void) { int fd=3,min=1;\n'
        'char *passwd="SECRET_CANARY",*cdkey="fixture",*ip="127.0.0.1";\n'
        'char *sqlstr="INSERT SECRET_CANARY";\n' + "\n".join(calls) + '\nreturn 0;}\n')
    subprocess.run(["gcc", "-O1", "-D_FORTIFY_SOURCE=2", "-Werror=format",
                    "-o", str(binary), str(c_file)], check=True)
    output = subprocess.check_output([str(binary)])
    assert b"SECRET_CANARY" not in output and output.count(b"[redacted]") == 4
print(json.dumps({"status": "passed", "native_logging_paths": 4,
                  "ordinary_debug_and_registration_redacted": True}))
