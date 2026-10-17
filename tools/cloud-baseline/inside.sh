set -euo pipefail
ulimit -t 90
ulimit -v 2097152
ulimit -u 128
cat /proc/net/dev > /logs/runtime-network.txt
cat /proc/net/route >> /logs/runtime-network.txt
mkdir -p /run-test/db
DB=/deps/usr/sbin/mariadbd
if test ! -e /run-test/db/sa/user_table.frm; then
$DB --no-defaults --bootstrap --user=root --datadir=/run-test/db --basedir=/deps/usr --lc-messages-dir=/deps/usr/share/mariadb --skip-log-bin --innodb-buffer-pool-size=32M < /schema.sql > /logs/db-bootstrap.log 2>&1
fi
$DB --no-defaults --user=root --datadir=/run-test/db --basedir=/deps/usr --lc-messages-dir=/deps/usr/share/mariadb --skip-grant-tables --skip-log-bin --bind-address=127.0.0.1 --port=13306 --socket='' --pid-file=/tmp/db.pid --innodb-buffer-pool-size=32M > /logs/db-start.log 2>&1 &
dbpid=$!
trap 'kill -TERM ${gpid:-} ${apid:-} $dbpid 2>/dev/null || true; wait || true' EXIT
sleep 3
kill -0 $dbpid
(cd saac && exec ./saacjt.exe) > /logs/saac-start.raw 2>&1 &
apid=$!
sleep 3
kill -0 $apid
(cd gmsv && exec ./gmsvjt.exe) > /logs/gmsv-start.raw 2>&1 &
gpid=$!
sleep 15
kill -0 $apid
kill -0 $gpid
cat /proc/net/tcp > /logs/runtime-tcp.txt
printf 'PROCESSES_SURVIVED\n'
