# Stone Age isolated baseline validation

Initial validation completed 2026-10-17 03:23:52 UTC. The final sanitized branch content was rebuilt and revalidated from a fresh pinned checkout on 2026-10-17 at 05:48 UTC. Scope: source compilation, isolated startup and SAAC/GMSV handshake only.

## Result
Pinned repository: https://github.com/xiangpeng19/stone-age/tree/0c58fb6683a49a178a8ad845a8c296c2cb83bd81

Eight-file compatibility/isolation patch plus sanitize-test-inputs.py applied; fresh x86-64 SAAC and GMSV executables compiled and linked with GCC 14.2.0. The patch and sanitization preserve the upstream GB18030 source encoding. Do not convert it to UTF-8 before applying.

The final test passed all six assertions in evidence/test-results.json (the final sanitized validation result):
- SAAC entered its event loop (开始工作).
- GMSV completed account-server authentication (与AC服务器连接成功！).
- Both processes remained alive at the 15-second observation point.
- Only 127.0.0.1:13306 (database), :19300 (SAAC), :19065 (GMSV) listened.
- Network namespace contained only loopback and no routes.

700 maps and 2,981 warp points loaded. Processes stopped after the test, and the temporary database was deleted. No historical account/character/mail/GM data was used; no game accounts were created. During that validation, no public port, repository push or Web client deployment occurred. This branch now saves the compatibility changes and reproduction inputs. The new commit does not add executable binaries, game assets, account data, database files or real credentials; pre-existing upstream repository content is unchanged.

## Limits and findings
This is not a playable-game or production-readiness verdict. Client login, character creation, combat, trade, save/reload, concurrency, long-running stability, performance and full security remain untested. No Web client exists from this work.

GCC 14 required legacy compatibility flags including -fpermissive: 103 SAAC and 2,563 GMSV warning occurrences remain in the final build (the initial SAAC build had 106). Initial GMSV build failed before this flag was added. Full historical build logs are not committed; the sanitized summary in evidence/test-results.json records the warning counts. SQL concatenation/plaintext-password design and broader 64-bit correctness still require modernization. Removing an unused _BACK_DOOR definition does not establish a confirmed backdoor was removed.

Runtime reported malformed encounter/group records, NPC quiz configuration errors, and missing fusion-pet data (needitemeneny.txt). These did not prevent startup but require gameplay validation. Initial database startup with a UNIX-domain socket failed under the environment restrictions; the successful run disabled that socket and used isolated TCP only.

## Reproduction
Use an authorized disposable x86-64 Debian Linux environment with GCC 14, GNU make, git, Python 3, zlib development headers, binutils, file, bubblewrap and util-linux unshare. All scripts are meant for this isolated test, never an existing or public database. The namespace must support unprivileged user/network isolation; if it fails, stop rather than running the servers outside isolation.

1. Copy this tools/cloud-baseline directory to a disposable working directory (or work directly inside it). Create logs and deps/root. Clone the repository into src, check out the pinned commit above and verify it. Do not execute bundled repository binaries. The branch source is already patched; this reproduction harness deliberately builds a separate pristine pinned checkout.
2. Obtain the exact official Debian packages listed in DEPENDENCIES.md, verify with sha256sum -c SHA256SUMS, extract with dpkg-deb -x into deps/root, and create deps/root/usr/include/mysql -> mariadb. No installation into the host is required.
3. bash validated-build.sh (applies patch once, then compiles both services).
4. (cd src && python3 ../prepare-runtime.py). The generator rejects an existing baseline-runtime directory.
5. timeout --signal=TERM 45s unshare -Urn python3 run-isolated.py >logs/runtime-result.log 2>&1
6. python3 verify-results.py
7. After checking all processes exited, remove src/baseline-runtime/db. Preserve logs.

run-isolated.py must only be invoked through unshare -Urn. It brings up loopback and invokes bubblewrap with no host home/config mount, empty environment and private PID/IPC/UTS namespaces. inside.sh applies CPU, address-space and process limits. The temporary database has no accounts and grant checks disabled only inside this no-egress namespace. fixture-only is a public disposable inter-service marker, not a real credential.

The saved build wrapper, sanitization script, fixture generator and isolated runtime harness were all rerun successfully from a fresh pinned checkout. The eight resulting source files were compared byte-for-byte with the files saved in this branch. Shell syntax and Python parsing checks also passed.

## Test-only sanitization before saving

Inherited client-protocol key values were replaced with the public string BASELINE, and commented old values were removed. These markers are not real credentials and do not support real clients or production use. The SAAC/GMSV disposable fixture password is separate.

The legacy SIGUSR1 file/shell administrative handler is disabled. A commented, already-disabled VIP check and alternate password suffix were removed; both services use only the configured service password. An always-true connection-capacity condition was simplified to remove hardcoded account-name exceptions and its out-of-bounds connection-array access. Normal source-author attribution is preserved.

The sanitizer contains no inherited sensitive values. The original patch is kept separately so reproduction does not require a diff containing removed credentials. The repository's existing history is not rewritten or claimed to be scrubbed. This remains a narrowly scoped isolated baseline, not a full security audit.
