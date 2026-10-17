#!/bin/bash
set -euo pipefail
ulimit -c 0
ulimit -t 1800
ulimit -v 2097152
ulimit -u 128
cleanup() {
    for task_pid in ${webpid:-} ${gpid:-} ${apid:-} ${dbpid:-}; do
        kill -TERM "$task_pid" 2>/dev/null || true
    done
    wait || true
    printf 'DEMO_PROCESSES_STOPPED\n'
}
trap cleanup EXIT
trap 'exit 0' TERM INT
cat /proc/net/dev > /logs/runtime-network.txt
cat /proc/net/route >> /logs/runtime-network.txt
mkdir /run-test/db
DB=/deps/usr/sbin/mariadbd
$DB --no-defaults --bootstrap --user=root --datadir=/run-test/db --basedir=/deps/usr --lc-messages-dir=/deps/usr/share/mariadb --skip-log-bin --innodb-buffer-pool-size=32M < /schema.sql > /logs/db-bootstrap.log 2>&1
$DB --no-defaults --user=root --datadir=/run-test/db --basedir=/deps/usr --lc-messages-dir=/deps/usr/share/mariadb --skip-grant-tables --skip-log-bin --bind-address=127.0.0.1 --port=13306 --socket='' --pid-file=/tmp/db.pid --innodb-buffer-pool-size=32M > /logs/db-start.log 2>&1 &
dbpid=$!
sleep 3
kill -0 "$dbpid"
(cd saac && exec ./saacjt.exe) > /logs/saac-start.log 2>&1 &
apid=$!
sleep 3
kill -0 "$apid"
(cd gmsv && exec ./gmsvjt.exe) > /logs/gmsv-start.log 2>&1 &
gpid=$!
sleep 10
kill -0 "$gpid"
cat /proc/net/tcp > /logs/native-listeners.txt
python3 /web-demo/gateway.py --socket /bridge/gateway.sock --runtime /run-test --log /logs/gateway-events.jsonl --port "$DEMO_PORT" > /logs/gateway.log 2>&1 &
webpid=$!
while kill -0 "$dbpid" && kill -0 "$apid" && kill -0 "$gpid" && kill -0 "$webpid"; do
    sleep 2
done
exit 1
