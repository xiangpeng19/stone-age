#!/usr/bin/env python3
"""Exercise the actual NPC file reader with a long valid fixture path."""
from pathlib import Path
import json
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

def function(data):
    start = data.index(b"static char *NPC_Util_MargeStrFromArgFile(")
    opening = data.index(b"{", start)
    cursor, depth = opening+1, 1
    while depth:
        depth += (data[cursor] == 123) - (data[cursor] == 125)
        cursor += 1
    return data[start:cursor].decode("ascii")

before = subprocess.check_output(["git","show","HEAD:gmsv/npc/npcutil.c"],cwd=ROOT)
after = (ROOT/"gmsv/npc/npcutil.c").read_bytes()
with tempfile.TemporaryDirectory(prefix="stoneage-npc-long-path-") as directory:
    directory = Path(directory)
    filename = "argument-fixture-with-long-filename.txt"
    (directory/filename).write_text("first\nsecond\n")
    results = {}
    for name, data in (("before",before),("after",after)):
        c_file, binary = directory/(name+".c"), directory/name
        c_file.write_text(
            "#include <stdio.h>\n#include <string.h>\n#include <limits.h>\n"
            "#define NPC_UTIL_GETARGSTR_LINEMAX 4096\n"
            "static const char *directory;\n"
            "static const char *getNpcdir(void) {return directory;}\n"
            "static void strcatsafe(char *dest,int len,const char *src) {\n"
            "strncat(dest,src,(size_t)len-strlen(dest)-1);}\n"
            "static void chompex(char *line) {line[strcspn(line,\"\\r\\n\")]=0;}\n"
            + function(data) +
            "\nint main(int argc,char **argv) {\n"
            "char output[128]=\"sentinel\"; directory=argv[1];\n"
            "char *result=NPC_Util_MargeStrFromArgFile(argv[2],output,sizeof(output));\n"
            "if(!result) return output[0]==0?3:4;\n"
            "return strcmp(output,\"first|second\");}\n")
        subprocess.run(["gcc","-O1","-g","-D_FORTIFY_SOURCE=2",
                        "-fstack-protector-strong","-o",str(binary),str(c_file)],check=True)
        results[name] = subprocess.run([str(binary),str(directory),filename],capture_output=True)
    assert results["before"].returncode == -6, results["before"].returncode
    assert b"buffer overflow detected" in results["before"].stderr
    assert results["after"].returncode == 0, results["after"].stderr
    oversized = subprocess.run([str(directory/"after"),str(directory),"x"*4096],capture_output=True)
    assert oversized.returncode == 3, oversized.returncode
    print(json.dumps({"status":"passed","original_aborted_on_long_path":True,
                      "long_valid_path_loaded":True,"oversized_path_rejected":True,
                      "fortify_enabled":True}))
