"""Small allowlisted native client. No packet or credential logging."""
import asyncio
import hashlib
from pathlib import Path
import re
import sys
import time

LIFECYCLE = Path(__file__).resolve().parents[1] / "cloud-lifecycle"
sys.path.insert(0, str(LIFECYCLE))
from fixtures import ACCOUNT, PASSWORD, NAME
from protocol import encode_packet, decode_packet

MAP_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIRECTIONS = {"north": b"a", "east": b"c", "south": b"e", "west": b"g"}


class DemoError(Exception):
    """Only a fixed, non-sensitive code is sent to browsers/logs."""


def map_number(token, *, empty_zero=False):
    if not token and empty_zero:
        return 0
    if not token or len(token) > 8:
        raise DemoError("invalid_map")
    value = 0
    for char in token.decode("ascii"):
        if char not in MAP_ALPHABET:
            raise DemoError("invalid_map")
        value = value * 62 + MAP_ALPHABET.index(char)
    return value


def parse_map(fields):
    floor, x1, y1, x2, y2, payload = fields
    width, height = x2-x1, y2-y1
    if not (floor == 1006 and 0 <= x1 < x2 <= 64 and 0 <= y1 < y2 <= 64):
        raise DemoError("invalid_map")
    sections = payload.split(b"|")
    if len(sections) != 4:
        raise DemoError("invalid_map")
    count = width * height
    layers = []
    for index, section in enumerate(sections[1:]):
        tokens = section.split(b",")
        if len(tokens) != count:
            raise DemoError("invalid_map")
        layers.append([map_number(token, empty_zero=index > 0) for token in tokens])
    return {"floor": floor, "bounds": [x1, y1, x2, y2], "width": width,
            "height": height, "name": sections[0].decode("gb18030", errors="replace"),
            "tiles": layers[0], "objects": layers[1], "events": layers[2]}


def saved_state(runtime):
    matches = []
    for path in (Path(runtime)/"saac/char").rglob("*.char"):
        raw = path.read_bytes()
        if raw.startswith(NAME+b"|"):
            matches.append((path, raw))
    if len(matches) != 1:
        return None
    path, raw = matches[0]
    document = raw.split(b"|", 2)[2].replace(b"\\n", b"\n")
    values = {}
    for name in (b"fl", b"x", b"y", b"lv", b"gld"):
        match = re.search(rb"(?:^|\n)"+name+rb"=(-?\d+)(?:\n|$)", document)
        if match is None:
            return None
        values[name.decode()] = int(match[1])
    return {"position": {"floor": values["fl"], "x": values["x"], "y": values["y"]},
            "level": values["lv"], "gold": values["gld"],
            "sha256": hashlib.sha256(raw).hexdigest()}


class NativeClient:
    def __init__(self, runtime):
        self.runtime = Path(runtime)
        self.reader = self.writer = None
        self.key = ACCOUNT + b"BASELINE"
        self.position = None

    async def send(self, opcode, fields, *, login=False):
        self.writer.write(encode_packet(opcode, fields, b"BASELINE" if login else self.key))
        await self.writer.drain()

    async def receive(self, timeout):
        line = await asyncio.wait_for(self.reader.readuntil(b"\n"), timeout)
        if len(line) > 65500:
            raise DemoError("native_protocol_error")
        packet = decode_packet(line, self.key)
        if packet.checksum_ok is False:
            raise DemoError("native_protocol_error")
        return packet

    async def wait(self, opcode, predicate=lambda packet: True, timeout=10):
        end = time.monotonic()+timeout
        for _ in range(2048):
            remaining = end-time.monotonic()
            if remaining <= 0:
                break
            packet = await self.receive(remaining)
            if packet.opcode == opcode and predicate(packet):
                return packet
        raise DemoError("native_timeout")

    async def drain(self):
        end = time.monotonic()+0.6
        while time.monotonic() < end:
            try:
                await self.receive(min(0.15, end-time.monotonic()))
            except asyncio.TimeoutError:
                return

    async def query_position(self):
        await self.send(45, [b"C"])
        packet = await self.wait(46, lambda item: item.fields[0].startswith(b"C"))
        values = packet.fields[0][1:].split(b"|")
        if len(values) != 5:
            raise DemoError("native_protocol_error")
        floor, width, height, x, y = map(int, values)
        if not (floor == 1006 and 0 <= x < width <= 64 and 0 <= y < height <= 64):
            raise DemoError("unsupported_map")
        self.position = {"floor": floor, "width": width, "height": height, "x": x, "y": y}
        return self.position.copy()

    async def enter(self):
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", 19065, limit=131072), 5)
        greeting = await asyncio.wait_for(self.reader.readexactly(2), 5)
        if greeting[1:] != b"\0":
            raise DemoError("native_protocol_error")
        await self.send(71, [ACCOUNT, PASSWORD], login=True)
        reply = await self.wait(72)
        if reply.fields != (b"ok",):
            raise DemoError("native_login_failed")
        await self.send(79, [])
        listing = await self.wait(80)
        if listing.fields[0] != b"successful":
            raise DemoError("native_login_failed")
        created = False
        if NAME not in listing.fields[1]:
            if listing.fields[1]:
                raise DemoError("unexpected_fixture_character")
            await self.send(73, [0, NAME, 100000, 30000, 3, 4, 6, 7, 10, 0, 0, 0, 0])
            reply = await self.wait(74)
            if reply.fields[0] != b"successful":
                raise DemoError("character_creation_failed")
            created = True
        await self.send(77, [NAME])
        reply = await self.wait(78)
        if reply.fields[0] != b"successful":
            raise DemoError("character_entry_failed")
        await self.drain()
        position = await self.query_position()
        await self.send(45, [b"P"])
        status = await self.wait(46, lambda item: item.fields[0].startswith(b"P1|"))
        fields = status.fields[0].split(b"|")
        if len(fields) != 32 or fields[28] != b"0" or fields[29] != NAME:
            raise DemoError("native_status_contract_error")
        await self.send(38, [position["floor"], 0, 0, position["width"], position["height"]])
        map_packet = await self.wait(39)
        map_data = parse_map(map_packet.fields)
        return {"online": True, "character": NAME.decode(), "created": created,
                "position": position, "map": map_data,
                "stats": {"level": int(fields[11]), "gold": int(fields[21])},
                "saved": saved_state(self.runtime)}

    async def move(self, direction):
        before = self.position.copy()
        await self.send(0, [before["x"], before["y"], DIRECTIONS[direction]])
        await asyncio.sleep(0.35)
        after = await self.query_position()
        if max(abs(after["x"]-before["x"]), abs(after["y"]-before["y"])) > 1:
            raise DemoError("unexpected_movement")
        return {"online": True, "position": after, "blocked": after == before,
                "saved": saved_state(self.runtime)}

    async def confirm_save(self):
        position = await self.query_position()
        end = time.monotonic()+30
        while time.monotonic() < end:
            state = saved_state(self.runtime)
            if state and all(state["position"][key] == position[key] for key in ("floor", "x", "y")):
                return {"online": True, "position": position, "saved": state,
                        "save_confirmed": True, "mechanism": "native_autosave"}
            await asyncio.sleep(0.25)
        raise DemoError("save_timeout")

    async def logout(self):
        await self.send(81, [])
        reply = await self.wait(82)
        if reply.fields != (b"successful", b"success"):
            raise DemoError("logout_failed")
        await asyncio.sleep(0.3)
        return {"online": False, "normal_logout": True, "saved": saved_state(self.runtime)}

    async def close(self):
        writer, self.writer = self.writer, None
        self.reader = None
        if writer is not None:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (OSError, ConnectionError, asyncio.TimeoutError):
                pass
            finally:
                writer.transport.abort()
