# P1 compatibility contract

`gmsv/char/char.c:CHAR_makeStatusString` emits the complete P1 status packet.
Its 28 numeric placeholders previously had only 27 arguments. Removing a
placeholder would move the following character name and title on the wire.

The first 27 values retain their original expressions and order. Numeric slot
28 is now explicit reserved zero. Its historical meaning is **unverified**:
this repository has no authoritative desktop-client consumer, and the separate
partial-status bitmask table does not establish the missing P1 field's meaning.
No gameplay meaning is assigned to the reserved value.

Splitting the payload on `|` yields 32 fields: `P1`, numeric slots 1–28, name at
index 29, title at index 30, then an empty trailing field. The strict native
formatter test checks the printf argument count and layout; the lifecycle test
checks the actual server packet, including the fixed fixture name's position.

The disposable fixture password is `demo-pass` (9 ASCII bytes); the incorrect
test value is `bad-demo` (8 bytes). Both fit native `PASSWDLEN=16` including NUL.
Login now uses a bounded decoder and rejects oversized fields without
truncation. Boundary tests cover 15-byte acceptance and 16-byte rejection with
a neighbouring canary. This is a source-level capacity fix and a checked
boundary test, not a claim of a demonstrated exploit.

Ordinary login, debug login/shutdown, and registration-query logging no longer
print passwords. The lifecycle wire log redacts the entire login packet, and a
runtime check searches generated logs for both plaintext fixture values and
their encoded login packets. The web gateway uses only the codec module.
