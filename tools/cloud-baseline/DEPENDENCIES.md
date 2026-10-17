# Official Debian dependency inputs
Downloaded and extracted into a private workspace, not system-installed. SHA256 of each downloaded package is in SHA256SUMS and evidence/toolchain.txt. Save each package under the listed deps/ filename, then run sha256sum -c SHA256SUMS before extraction.

- deps/libmariadb-dev.deb: https://deb.debian.org/debian/pool/main/m/mariadb/libmariadb-dev_11.8.6-0+deb13u1_amd64.deb
- deps/libmariadb3.deb: https://deb.debian.org/debian/pool/main/m/mariadb/libmariadb3_11.8.6-0+deb13u1_amd64.deb
- deps/server-core.deb: https://deb.debian.org/debian/pool/main/m/mariadb/mariadb-server-core_11.8.6-0+deb13u1_amd64.deb
- deps/liburing.deb: https://deb.debian.org/debian/pool/main/libu/liburing/liburing2_2.9-1_amd64.deb
- deps/libaio.deb: https://deb.debian.org/debian/pool/main/liba/libaio/libaio1t64_0.3.113-8+b1_amd64.deb

Use these sources with the pinned package checksums, not an arbitrary mirror or binary from the game repository. Package availability can change.
