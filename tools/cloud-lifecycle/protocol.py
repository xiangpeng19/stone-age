"""Stone Age public-baseline wire codec; no socket or credential handling.

Reference: gmsv/autil.c, gmsv/include/autil.h, gmsv/lssproto_serv.c.
The native protocol assumes a 32-bit little-endian int. Fields use the public
BASELINE marker for ClientLogin, then account + BASELINE, including its reply.
All packets end with LF; the initial server greeting is separate and ends NUL.
Run this file directly for deterministic codec self-tests.
"""

from dataclasses import dataclass
import struct
from typing import Iterable, Optional, Union

TABLE = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz{}"
DEFAULT_KEY = b"BASELINE"
Value = Union[int, bytes, str]

# Schemas omit the final checksum field. 's' yields bytes, never lossy Unicode.
CLIENT_SCHEMAS = {
    0: "iis", 1: "iis", 38: "iiiii", 40: "i", 45: "s", 70: "iii",
    71: "ss", 73: "isiiiiiiiiiii", 75: "s", 77: "s", 79: "", 81: "",
    83: "", 85: "", 87: "s",
}
SERVER_SCHEMAS = {
    2: "iii", 4: "ii", 7: "ii", 12: "s", 13: "s", 15: "s", 22: "s",
    24: "ii", 26: "isi", 28: "iiiiiiis", 30: "s", 31: "is", 36: "isi",
    37: "iiiiiiiis", 39: "iiiiis", 41: "s", 42: "s", 43: "s", 44: "s",
    46: "s", 47: "iiis", 49: "i", 51: "i", 53: "ii", 55: "ii",
    59: "iiii", 63: "i", 66: "iiiis", 68: "iis", 69: "iiii",
    72: "s", 74: "ss", 76: "ss", 78: "ss", 80: "ss", 82: "ss",
    84: "s", 86: "ii", 88: "s", 90: "i", 92: "s", 93: "s", 95: "i",
    100: "ii", 101: "i", 107: "ii", 115: "ii",
}


def as_bytes(value: Union[bytes, str]) -> bytes:
    """ASCII test strings may be passed as str; use bytes for game text."""
    return value.encode("ascii") if isinstance(value, str) else bytes(value)


def int32(value: int) -> int:
    return ((value + 0x80000000) & 0xffffffff) - 0x80000000


def swap4(value: bytes, rule: str) -> bytes:
    out = bytearray(4)
    for i, place in enumerate(rule):
        out[int(place) - 1] = value[i]
    return bytes(out)


def encode64(data: bytes, key: bytes = b"", shift: int = 0) -> bytes:
    """C util_256to64 and keyed variants, including omitted zero tail bits."""
    out = bytearray()
    dw = 0

    def emit(value: int) -> None:
        adjustment = shift * key[len(out) % len(key)] if key else 0
        out.append(TABLE[(value + adjustment) % 64])

    for i, value in enumerate(data):
        dw |= value << ((i % 3) * 2)
        emit(dw & 63)
        dw >>= 6
        if i % 3 == 2:
            emit(dw & 63)
            dw = 0
    if dw:
        emit(dw)
    return bytes(out)


def decode64(data: bytes, key: bytes = b"", shift: int = 0) -> bytes:
    """C util_64to256; shift reverses the matching encoder adjustment."""
    out = bytearray()
    dw = 0
    for i, char in enumerate(data):
        value = TABLE.index(char)
        if key:
            value = (value + shift * key[i % len(key)]) % 64
        if i % 4:
            dw |= value << ((4 - i % 4) * 2)
            out.append(dw & 255)
            dw >>= 8
        else:
            dw = value
    if dw:
        out.append(dw & 255)
    return bytes(out)


def encode_int(value: int, key: Union[bytes, str] = DEFAULT_KEY) -> bytes:
    key = as_bytes(key) or DEFAULT_KEY
    raw = swap4(struct.pack("<I", value & 0xffffffff), "3142")
    return encode64(bytes(b ^ 255 for b in raw), key, +1)


def decode_int(data: bytes, key: Union[bytes, str] = DEFAULT_KEY) -> int:
    raw = decode64(data, as_bytes(key) or DEFAULT_KEY, -1)
    if len(raw) > 4:
        raise ValueError("Integer field has more than four decoded bytes")
    # C writes a terminator after decoding; a dropped zero tail is zero-filled.
    raw = raw.ljust(4, b"\0")
    raw = swap4(bytes(b ^ 255 for b in raw), "2413")
    return struct.unpack("<i", raw)[0]


def encode_string(value: Union[bytes, str], key: Union[bytes, str] = DEFAULT_KEY) -> bytes:
    value = as_bytes(value)
    if b"\0" in value:
        raise ValueError("The C protocol cannot represent embedded NUL strings")
    return encode64(value, as_bytes(key) or DEFAULT_KEY, -1)


def decode_string(data: bytes, key: Union[bytes, str] = DEFAULT_KEY) -> bytes:
    return decode64(data, as_bytes(key) or DEFAULT_KEY, +1).split(b"\0", 1)[0]


def encode_outer(raw: bytes, seed: int = 0) -> bytes:
    if not raw or not 0 <= seed < 99:
        raise ValueError("Nonempty message and seed in 0..98 required")
    prefix_raw = swap4(struct.pack("<I", seed), "2413")
    prefix = encode64(bytes(b ^ 255 for b in prefix_raw))
    assert len(prefix) == 6
    rotation = seed % len(raw)
    rotated = raw[rotation:] + raw[:rotation]
    return bytes(b ^ 255 for b in prefix + rotated) + b"\n"


def decode_outer(line: bytes) -> bytes:
    if line.endswith(b"\n"):
        line = line[:-1]
    if len(line) < 7:
        raise ValueError("Truncated outer message")
    data = bytes(b ^ 255 for b in line)
    raw_seed = decode64(data[:6]).ljust(4, b"\0")
    seed = struct.unpack("<I", swap4(bytes(b ^ 255 for b in raw_seed), "3142"))[0]
    payload = data[6:]
    rotation = seed % len(payload)
    return payload[-rotation:] + payload[:-rotation] if rotation else payload


def encode_packet(opcode: int, fields: Iterable[Value], key: Union[bytes, str] = DEFAULT_KEY,
                  seed: int = 0) -> bytes:
    encoded = []
    checksum = 0
    for field in fields:
        if isinstance(field, int):
            checksum += field
            encoded.append(encode_int(field, key))
        else:
            field = as_bytes(field)
            checksum += len(field)
            encoded.append(encode_string(field, key))
    encoded.append(encode_int(int32(checksum), key))
    raw = b"&;" + str(opcode).encode("ascii") + b";" + b";".join(encoded) + b";#;"
    return encode_outer(raw, seed)


@dataclass(frozen=True)
class Packet:
    opcode: int
    fields: tuple
    checksum: int
    checksum_ok: Optional[bool]
    raw: bytes
    encoded_fields: tuple


def decode_packet(line: bytes, key: Union[bytes, str] = DEFAULT_KEY,
                  schema: Optional[str] = None) -> Packet:
    raw = decode_outer(line)
    parts = raw.split(b";")
    if len(parts) < 5 or parts[0] != b"&" or parts[-2:] != [b"#", b""]:
        raise ValueError("Malformed message delimiters")
    opcode = int(parts[1])
    encoded_fields = tuple(parts[2:-3])
    checksum = decode_int(parts[-3], key)
    if schema is None:
        schema = SERVER_SCHEMAS.get(opcode)
    if schema is None:
        return Packet(opcode, (), checksum, None, raw, encoded_fields)
    if len(schema) != len(encoded_fields):
        raise ValueError(f"Opcode {opcode}: expected {len(schema)} fields, got {len(encoded_fields)}")
    values = []
    checksum_calc = 0
    for field_type, encoded in zip(schema, encoded_fields):
        if field_type == "i":
            value = decode_int(encoded, key)
            checksum_calc += value
        elif field_type == "s":
            value = decode_string(encoded, key)
            checksum_calc += len(value)
        else:
            raise ValueError(f"Unknown field type {field_type!r}")
        values.append(value)
    return Packet(opcode, tuple(values), checksum, int32(checksum_calc) == checksum,
                  raw, encoded_fields)


def self_test() -> None:
    """Round trips plus independent, literal C-reference golden outputs."""
    # Produced by compiling the exact functions from gmsv/autil.c with GCC,
    # then calling util_mkint/util_mkstring through ctypes (BASELINE key).
    int_goldens = {
        0: b"10I4BC", 1: b"1024BC", -1: b"21J5C", 17: b"1020BC",
        255: b"10Y5BC", 256: b"00I4BC", 65535: b"2zY5BC",
        0x12345678: b"htHcNC", 0x7fffffff: b"21R5C", -0x80000000: b"10A4BC",
    }
    string_goldens = {
        b"": b"", b"ok": b"jip", b"no": b"iyp",
        b"baseline_user": b"W4ZNPe8LiKZIf49Km0",
        b"TestCharacter": b"IKZNe4sLV84JN89Km0",
    }
    for value, expected in int_goldens.items():
        assert encode_int(value) == expected
        assert decode_int(expected) == value
    for value, expected in string_goldens.items():
        assert encode_string(value) == expected
        assert decode_string(expected) == value
    for key in (DEFAULT_KEY, b"baseline_userBASELINE"):
        for value in (0, 1, -1, 17, 255, 256, 65535, 0x12345678, 0x7fffffff, -0x80000000):
            assert decode_int(encode_int(value, key), key) == value
        for value in (b"", b"ok", b"no", b"baseline_user", b"TestCharacter", bytes(range(1, 256))):
            assert decode_string(encode_string(value, key), key) == value
        for seed in range(99):
            line = encode_packet(71, [b"baseline_user", b"test_only"], key, seed)
            packet = decode_packet(line, key, CLIENT_SCHEMAS[71])
            assert packet.fields == (b"baseline_user", b"test_only")
            assert packet.checksum_ok
    assert encode64(b"\xff\xff\xff\xff") == b"}}}}}3"
    assert encode64(b"\x00\x00\x00\x00") == b"00000"
    print("Protocol self-tests passed")


if __name__ == "__main__":
    self_test()
