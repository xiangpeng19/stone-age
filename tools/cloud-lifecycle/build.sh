#!/bin/bash
# Uses the exact extracted MariaDB development packages documented in cloud-baseline.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
: "${DEPS_ROOT:?Set DEPS_ROOT to the extracted dependency directory}"
: "${LOG_DIR:?Set LOG_DIR to a fresh evidence directory}"
mkdir -p "$LOG_DIR"
make -B -C "$ROOT/saac" -j2 CFLAGS="-O1 -g -std=gnu99 -fgnu89-inline -fcommon -fpermissive -Wall -Wextra \$(INCFLAGS) -I$DEPS_ROOT/usr/include -I$DEPS_ROOT/usr/include/mariadb" MYSQL="-L$DEPS_ROOT/usr/lib/x86_64-linux-gnu -Wl,-rpath,$DEPS_ROOT/usr/lib/x86_64-linux-gnu -lmariadb -lz" >"$LOG_DIR/saac-build.log" 2>&1
make -B -C "$ROOT/gmsv" -j2 CFLAGS='-O1 -g -std=gnu99 -fgnu89-inline -fcommon -fpermissive -Wall -Wextra $(INCFLAGS)' >"$LOG_DIR/gmsv-build.log" 2>&1
