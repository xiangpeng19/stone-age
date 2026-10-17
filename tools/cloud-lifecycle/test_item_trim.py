#!/usr/bin/env python3
"""Regression for long item lines; runs only temporary native test binaries."""
from pathlib import Path
import json
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

def block(data):
    start = data.index(b"\t\titemnum ++;\n{\n", data.index(b"ITEM_readItemConfFile"))
    start += len(b"\t\titemnum ++;\n")
    end = data.index(b"\n{\n\t\tchar    token[256];", start)
    return data[start:end].decode("ascii")

cases = [" " + "x"*328, "", "abc", " abc", "     abc", "   ", " " + "x"*3000, "\tabc"]
before = subprocess.check_output(["git", "show", "HEAD:gmsv/item/item.c"], cwd=ROOT)
after = (ROOT/"gmsv/item/item.c").read_bytes()
with tempfile.TemporaryDirectory(prefix="stoneage-item-trim-") as directory:
    directory = Path(directory)
    results = {}
    for name, data in (("before", before), ("after", after)):
        c_file = directory/(name+".c")
        binary = directory/name
        c_file.write_text(
            "#include <stdio.h>\n#include <string.h>\n"
            "static void trim(char *line) { int i;\n" + block(data) + "\n}\n"
            "int main(void) {\nchar line[4096];\nconst char *inputs[] = {" +
            ",".join(json.dumps(value) for value in cases) + "};\n"
            "const char *expected[] = {" +
            ",".join(json.dumps(value.lstrip(" ")) for value in cases) + "};\n"
            "for (size_t k=0;k<sizeof(inputs)/sizeof(inputs[0]);k++) {\n"
            "strcpy(line,inputs[k]); trim(line); if(strcmp(line,expected[k])) return 2;\n"
            "}\nreturn 0;\n}\n")
        subprocess.run(["gcc", "-O1", "-g", "-D_FORTIFY_SOURCE=2",
                        "-fstack-protector-strong", "-o", str(binary), str(c_file)], check=True)
        results[name] = subprocess.run([str(binary)], capture_output=True)
    assert results["before"].returncode == -6, results["before"].returncode
    assert b"buffer overflow detected" in results["before"].stderr
    assert results["after"].returncode == 0, results["after"].stderr
    print(json.dumps({"status":"passed", "original_aborted_on_long_line":True,
                      "fortify_enabled":True, "patched_cases":len(cases)}))
