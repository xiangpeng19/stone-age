#!/usr/bin/env python3
"""Compile the actual P1 formatter with strict printf argument checking."""
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "gmsv/char/char.c").read_bytes()
start = source.index(b"\t\tsnprintf(CHAR_statusSendBuffer", source.index(b"char* CHAR_makeStatusString"))
end = source.index(b"\t\tstrlength = strlen( CHAR_statusSendBuffer );", start)
statement = source[start:end].decode("ascii")
symbols = sorted(set(re.findall(r"CHAR_[A-Z][A-Z0-9_]+", statement)))
with tempfile.TemporaryDirectory(prefix="stoneage-p1-contract-") as directory:
    directory = Path(directory)
    c_file, binary = directory / "p1.c", directory / "p1"
    c_file.write_text(
        "#include <stdio.h>\n#include <string.h>\n" +
        "\n".join(f"#define {symbol} {index+1}" for index, symbol in enumerate(symbols)) +
        "\n#define CHAR_getInt(index,field) (field)\n"
        "#define CHAR_getWorkInt(index,field) (field)\n"
        "int main(void) {\nchar CHAR_statusSendBuffer[4096];\n"
        "int exp=900,maxexp=1200,attr[4]={10,20,30,40};\n" + statement +
        '\nstrcat(CHAR_statusSendBuffer,"FixtureName|FixtureTitle|");\n'
        "fputs(CHAR_statusSendBuffer,stdout); return 0; }\n")
    subprocess.run(["gcc", "-O1", "-D_FORTIFY_SOURCE=2", "-fstack-protector-strong",
                    "-Wall", "-Wformat=2", "-Werror=format", "-o", str(binary), str(c_file)], check=True)
    fields = subprocess.check_output([str(binary)]).split(b"|")
    assert len(fields) == 32 and fields[0] == b"P1" and fields[-1] == b""
    assert all(re.fullmatch(rb"-?\d+", field) for field in fields[1:29])
    assert fields[28] == b"0"
    assert fields[29:31] == [b"FixtureName", b"FixtureTitle"]
print(json.dumps({"status": "passed", "numeric_slots": 28, "reserved_slot_28": 0,
                  "name_index": 29, "title_index": 30, "format_arguments_checked": True}))
