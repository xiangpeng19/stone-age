#!/bin/bash
set -euo pipefail
ulimit -t 120
ulimit -v 2097152
ulimit -u 128
cat /proc/net/dev > /logs/runtime-network.txt
cat /proc/net/route >> /logs/runtime-network.txt
mkdir -p /run-test/db
DB=/deps/usr/sbin/mariadbd
$DB --no-defaults --bootstrap --user=root --datadir=/run-test/db --basedir=/deps/usr --lc-messages-dir=/deps/usr/share/mariadb --skip-log-bin --innodb-buffer-pool-size=32M < /schema.sql > /logs/db-bootstrap.log 2>&1
$DB --no-defaults --user=root --datadir=/run-test/db --basedir=/deps/usr --lc-messages-dir=/deps/usr/share/mariadb --skip-grant-tables --skip-log-bin --bind-address=127.0.0.1 --port=13306 --socket='' --pid-file=/tmp/db.pid --innodb-buffer-pool-size=32M > /logs/db-start.log 2>&1 &
dbpid=$!
cleanup() {
    kill -TERM ${gpid:-} ${apid:-} "$dbpid" 2>/dev/null || true
    wait || true
    printf 'TEST_PROCESSES_STOPPED\n'
}
trap cleanup EXIT
sleep 3
kill -0 "$dbpid"
(cd saac && exec ./saacjt.exe) > /logs/saac-start.raw 2>&1 &
apid=$!
sleep 3
kill -0 "$apid"
(cd gmsv && exec ./gmsvjt.exe) > /logs/gmsv-start.raw 2>&1 &
gpid=$!
sleep 10
kill -0 "$gpid"
cat /proc/net/tcp > /logs/runtime-tcp.txt
python3 /test/lifecycle.py
kill -0 "$gpid"
kill -0 "$apid"
kill -0 "$dbpid"
printf 'LIFECYCLE_PASSED\n'
