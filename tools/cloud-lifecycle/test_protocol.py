#!/usr/bin/env python3
"""Reproducible codec cross-check against the repository's native C functions.

Run: python tools/cloud-lifecycle/test_protocol.py
Requires GCC and writes only a temporary C file/shared object in the OS tempdir.
No servers, sockets, accounts, or historical game data are accessed.
"""
import ctypes
from pathlib import Path
import random
import re
import subprocess
import tempfile
import unittest

import protocol


class NativeCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="stoneage-codec-")
        root = Path(__file__).resolve().parents[2]
        source = (root / "gmsv/autil.c").read_text(encoding="latin1")
        names = [
            "util_EncodeMessage", "util_DecodeMessage", "util_256to64",
            "util_64to256", "util_256to64_shr", "util_shl_64to256",
            "util_256to64_shl", "util_shr_64to256", "util_swapint",
            "util_xorstring", "util_shrstring", "util_shlstring",
            "util_deint", "util_mkint", "util_destring", "util_destring_bounded", "util_mkstring",
        ]
        chunks = []
        for name in names:
            match = re.search(r"(?m)^(?:void|int) " + name + r"\([^\n]*\)\n\{", source)
            if not match:
                raise AssertionError(f"Missing C reference function {name}")
            start = match.start()
            cursor = source.index("{", start) + 1
            depth = 1
            while depth:
                depth += (source[cursor] == "{") - (source[cursor] == "}")
                cursor += 1
            chunks.append(source[start:cursor])
        preamble = '''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#define DEFAULTTABLE "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz{}"
#define _DEFAULT_PKEY "BASELINE"
#define SLICE_SIZE 65500
#define SLICE_MAX 20
char PersonalKey[4096];
char *MesgSlice[20];
'''
        prototypes = "\n".join(c[:c.index("{")].strip() + ";" for c in chunks)
        c_file = Path(cls.temp.name) / "reference.c"
        library = Path(cls.temp.name) / "reference.so"
        c_file.write_text(preamble + prototypes + "\n" + "\n".join(chunks))
        subprocess.run(["gcc", "-shared", "-fPIC", "-O0", "-o", str(library), str(c_file)], check=True)
        cls.c = ctypes.CDLL(str(library))
        cls.key = (ctypes.c_char * 4096).in_dll(cls.c, "PersonalKey")
        cls.slices = (ctypes.c_char_p * 20).in_dll(cls.c, "MesgSlice")
        cls.libc = ctypes.CDLL(None)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_integer_fields(self):
        rng = random.Random(123)
        values = [0, 1, -1, 17, 255, 256, 65535, 0x12345678, 0x7fffffff, -0x80000000]
        values += [rng.randrange(-2**31, 2**31) for _ in range(1000)]
        for key in (b"BASELINE", b"baseline_userBASELINE"):
            self.key.value = key
            for value in values:
                encoded = ctypes.create_string_buffer(8192)
                self.c.util_mkint(encoded, ctypes.c_int(value))
                expected = encoded.value[1:]
                self.assertEqual(protocol.encode_int(value, key), expected)
                self.assertEqual(protocol.decode_int(expected, key), value)
                self.slices[0] = expected
                decoded = ctypes.c_int()
                self.c.util_deint(0, ctypes.byref(decoded))
                self.assertEqual(decoded.value, value)

    def test_string_fields(self):
        rng = random.Random(456)
        values = [b"", b"ok", b"no", b"baseline_user", b"TestCharacter", bytes(range(1, 256))]
        values += [bytes(rng.randrange(1, 256) for _ in range(rng.randrange(1, 300))) for _ in range(100)]
        for key in (b"BASELINE", b"baseline_userBASELINE"):
            self.key.value = key
            for value in values:
                encoded = ctypes.create_string_buffer(8192)
                self.c.util_mkstring(encoded, value)
                expected = encoded.value[1:]
                self.assertEqual(protocol.encode_string(value, key), expected)
                self.assertEqual(protocol.decode_string(expected, key), value)
                self.slices[0] = expected
                decoded = ctypes.create_string_buffer(8192)
                self.c.util_destring(0, decoded)
                self.assertEqual(decoded.value, value)

    def test_bounded_login_strings(self):
        class Guarded(ctypes.Structure):
            _fields_ = [("value", ctypes.c_char * 16), ("guard", ctypes.c_char * 8)]
        self.key.value = b"BASELINE"
        for length in (0, 1, 14, 15, 16, 22, 1024):
            plain = b"x" * length
            self.slices[0] = protocol.encode_string(plain)
            guarded = Guarded()
            guarded.guard = b"CANARY!"
            decoded = self.c.util_destring_bounded(0, ctypes.byref(guarded), 16)
            self.assertEqual(guarded.guard, b"CANARY!")
            if length <= 15:
                self.assertEqual(decoded, length)
                self.assertEqual(guarded.value, plain)
            else:
                self.assertEqual(decoded, -1)
                self.assertEqual(guarded.value, b"")

    def test_outer_packets(self):
        raw = b"&;79;10I4BC;#;"
        for initial in range(100):
            self.libc.srand(initial)
            seed = self.libc.rand() % 99
            self.libc.srand(initial)
            encoded = ctypes.create_string_buffer(8192)
            self.c.util_EncodeMessage(encoded, raw)
            self.assertEqual(protocol.encode_outer(raw, seed), encoded.value + b"\n")
            self.assertEqual(protocol.decode_outer(encoded.value), raw)
            decoded = ctypes.create_string_buffer(8192)
            self.c.util_DecodeMessage(decoded, ctypes.create_string_buffer(protocol.encode_outer(raw, seed)))
            self.assertEqual(decoded.value, raw)

    def test_packet_schemas(self):
        for schemas in (protocol.CLIENT_SCHEMAS, protocol.SERVER_SCHEMAS):
            for opcode, schema in schemas.items():
                fields = tuple(12345 if item == "i" else b"fixture" for item in schema)
                line = protocol.encode_packet(opcode, fields, b"baseline_userBASELINE")
                decoded = protocol.decode_packet(line, b"baseline_userBASELINE", schema)
                self.assertEqual(decoded.fields, fields)
                self.assertTrue(decoded.checksum_ok)

    def test_literal_goldens(self):
        protocol.self_test()


if __name__ == "__main__":
    unittest.main(verbosity=2)
