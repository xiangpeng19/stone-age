#!/usr/bin/env python3
"""Map-native compatibility and HTTP/WS boundary checks with no game services."""
import ctypes
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from aiohttp import ClientSession, UnixConnector, WSServerHandshakeError, web
from gateway import Gateway, make_runner, validate_request
from native import DemoError, map_number, parse_map

ROOT = Path(__file__).resolve().parents[2]


class MapContract(unittest.TestCase):
    def test_map_alphabet_against_native(self):
        source = (ROOT/"gmsv/util.c").read_bytes()
        start = source.index(b"char *cnv10to62(")
        opening = source.index(b"{", start)
        cursor, depth = opening+1, 1
        while depth:
            depth += (source[cursor] == 123) - (source[cursor] == 125)
            cursor += 1
        with tempfile.TemporaryDirectory() as directory:
            c_file, library = Path(directory)/"map.c", Path(directory)/"map.so"
            c_file.write_bytes(b"#include <stdio.h>\n"+source[start:cursor])
            subprocess.run(["gcc", "-shared", "-fPIC", "-O1", "-o", str(library), str(c_file)], check=True)
            native = ctypes.CDLL(str(library))
            native.cnv10to62.restype = ctypes.c_char_p
            for number in (0, 1, 10, 35, 36, 61, 62, 1006, 65535):
                buffer = ctypes.create_string_buffer(64)
                token = native.cnv10to62(number, buffer, 64)
                self.assertEqual(map_number(token), number)
            self.assertEqual(map_number(b"a"), 10)
            self.assertEqual(map_number(b"A"), 36)

    def test_clipped_bounds_and_empty_layers(self):
        result = parse_map((1006, 1, 2, 3, 4, b"Fixture|a,z,A,Z|,,1,|,2,,"))
        self.assertEqual(result["bounds"], [1, 2, 3, 4])
        self.assertEqual(result["tiles"], [10, 35, 36, 61])
        self.assertEqual(result["objects"], [0, 0, 1, 0])
        self.assertEqual(result["events"], [0, 2, 0, 0])
        for fields in ((1006, -1, 0, 1, 1, b"x|0,0|,|,"),
                       (1006, 0, 0, 2, 2, b"x|0|0|0")):
            with self.assertRaises(DemoError):
                parse_map(fields)

    def test_allowlist_has_no_identity_or_protocol_input(self):
        for data in ({"id": 1, "action": "enter", "password": "x"*16},
                     {"id": 1, "action": "enter", "account": "other"},
                     {"id": 1, "action": "enter", "host": "127.0.0.1"},
                     {"id": 1, "action": "raw", "packet": "anything"},
                     {"id": True, "action": "enter"},
                     {"id": 1, "action": "move", "direction": "teleport"}):
            with self.assertRaises(DemoError):
                validate_request(data)


class BoundaryContract(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name)
        self.runner = make_runner(Gateway(path, 18680, path/"events.jsonl"))
        await self.runner.setup()
        self.socket = path/"gateway.sock"
        await web.UnixSite(self.runner, str(self.socket)).start()
        self.client = ClientSession(connector=UnixConnector(path=str(self.socket)))
        self.headers = {"Host": "127.0.0.1:18680"}

    async def asyncTearDown(self):
        await self.client.close()
        await self.runner.cleanup()
        self.temp.cleanup()

    async def test_host_origin_and_invalid_frames(self):
        async with self.client.get("http://fixture/", headers=self.headers) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        for path, headers in (("/", {"Host": "other.example"}), ("/?ignored=x", self.headers)):
            async with self.client.get("http://fixture"+path, headers=headers) as response:
                self.assertEqual(response.status, 403)
        for origin in (None, "http://other.example", "null"):
            headers = dict(self.headers)
            if origin:
                headers["Origin"] = origin
            with self.assertRaises(WSServerHandshakeError) as error:
                await self.client.ws_connect("http://fixture/ws", headers=headers)
            self.assertEqual(error.exception.status, 403)
        headers = {**self.headers, "Origin": "http://127.0.0.1:18680"}
        async with self.client.ws_connect("http://fixture/ws", headers=headers) as ws:
            self.assertEqual((await ws.receive_json())["event"], "ready")
            await ws.send_str("not json")
            self.assertEqual((await ws.receive_json())["error"], "invalid_request")
            await ws.send_json({"id": 1, "action": "enter", "password": "x"*16})
            invalid = await ws.receive_json()
            self.assertEqual(invalid["error"], "invalid_request")
            self.assertEqual(invalid["id"], 1)
            await ws.send_bytes(b"binary")
            await ws.receive()
            self.assertEqual(ws.close_code, 1003)


if __name__ == "__main__":
    unittest.main(verbosity=2)
