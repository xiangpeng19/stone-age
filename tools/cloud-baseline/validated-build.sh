#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
test "$(git -C src rev-parse HEAD)" = 0c58fb6683a49a178a8ad845a8c296c2cb83bd81
# Apply validated-baseline.patch to a fresh pinned checkout, once.
# This patch preserves upstream GB18030 source encoding.
git -C src apply --check ../validated-baseline.patch
git -C src apply ../validated-baseline.patch
python3 sanitize-test-inputs.py src
make -B -C src/saac -j2 CFLAGS='-O1 -g -std=gnu99 -fgnu89-inline -fcommon -fpermissive -Wall -Wextra $(INCFLAGS) -I../../deps/root/usr/include -I../../deps/root/usr/include/mariadb' MYSQL="-L../../deps/root/usr/lib/x86_64-linux-gnu -Wl,-rpath,$PWD/deps/root/usr/lib/x86_64-linux-gnu -lmariadb -lz" >logs/saac-build-1.log 2>&1
make -B -C src/gmsv -j2 CFLAGS='-O1 -g -std=gnu99 -fgnu89-inline -fcommon -fpermissive -Wall -Wextra $(INCFLAGS)' >logs/gmsv-build-2.log 2>&1
