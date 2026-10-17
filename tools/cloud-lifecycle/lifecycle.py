#!/usr/bin/env python3
"""Black-box player lifecycle against isolated SAAC/GMSV fixture services."""
import hashlib
import json
from pathlib import Path
import re
import socket
import time
import traceback
from protocol import encode_packet, decode_packet

from fixtures import ACCOUNT, PASSWORD, WRONG_PASSWORD, NAME
KEY = ACCOUNT + b'BASELINE'
LOGS = Path('/logs')
EVENTS = []
WIRE = (LOGS/'wire.jsonl').open('w')


def text(value):
    return value.decode('gb18030', errors='replace') if isinstance(value, bytes) else value


def record(stage, **data):
    item = {'stage': stage, **data}
    EVENTS.append(item)
    print(json.dumps(item), flush=True)


class Client:
    def __init__(self):
        self.sock = socket.create_connection(('127.0.0.1', 19065), timeout=5)
        self.sock.settimeout(1)
        self.buffer = b''
        self.packets = []
        greeting = b''
        while len(greeting) < 2:
            block = self.sock.recv(2-len(greeting))
            if not block:
                raise EOFError('Server closed before greeting')
            greeting += block
        assert greeting[1:] == b'\0', greeting
        record('connected', greeting_hex=greeting.hex())

    def send(self, opcode, fields, login=False):
        packet = encode_packet(opcode, fields, b'BASELINE' if login else KEY)
        WIRE.write(json.dumps({'direction': 'client', 'opcode': opcode, 'redacted': True} if login else {'direction': 'client', 'opcode': opcode, 'fields': [text(x) for x in fields], 'wire_hex': packet.hex()})+'\n')
        WIRE.flush()
        self.sock.sendall(packet)

    def receive(self):
        while b'\n' not in self.buffer:
            block = self.sock.recv(65536)
            if not block:
                raise EOFError('Game server closed client connection')
            self.buffer += block
        line, self.buffer = self.buffer.split(b'\n', 1)
        packet = decode_packet(line+b'\n', KEY)
        WIRE.write(json.dumps({'direction': 'server', 'opcode': packet.opcode, 'fields': [text(x) for x in packet.fields], 'checksum_ok': packet.checksum_ok, 'raw_hex': packet.raw.hex(), 'wire_hex': (line+b'\n').hex()})+'\n')
        WIRE.flush()
        if packet.checksum_ok is not None:
            assert packet.checksum_ok, f'Invalid server checksum for {packet.opcode}'
        self.packets.append(packet)
        return packet

    def wait(self, opcode, predicate=lambda p: True, timeout=10):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            try:
                p = self.receive()
            except socket.timeout:
                continue
            if p.opcode == opcode and predicate(p):
                return p
        raise TimeoutError(f'No matching response opcode {opcode}')

    def drain(self, seconds=0.3):
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            try:
                self.receive()
            except socket.timeout:
                return

    def reject_wrong_password(self):
        self.send(71, [ACCOUNT, WRONG_PASSWORD], login=True)
        p = self.wait(72)
        assert p.fields[0] == b'no', p.fields
        record('wrong_password_rejected', result=text(p.fields[0]))

    def login(self):
        self.send(71, [ACCOUNT, PASSWORD], login=True)
        p = self.wait(72)
        assert p.fields == (b'ok',) or list(p.fields) == [b'ok'], p.fields
        record('account_login', result=text(p.fields[0]))

    def charlist(self):
        self.send(79, [])
        p = self.wait(80)
        assert p.fields[0] == b'successful', p.fields
        return p.fields[1]

    def enter(self):
        self.send(77, [NAME])
        p = self.wait(78)
        assert p.fields[0] == b'successful', p.fields
        self.drain()
        return self.position()

    def position(self):
        self.send(45, [b'C'])
        p = self.wait(46, lambda p: p.fields[0].startswith(b'C'))
        fields = p.fields[0][1:].split(b'|')
        assert len(fields) == 5, fields
        floor, width, height, x, y = map(int, fields)
        assert 0 <= x < width and 0 <= y < height
        return {'floor': floor, 'x': x, 'y': y, 'width': width, 'height': height}

    def player_state(self):
        self.send(45, [b'P'])
        p = self.wait(46, lambda p: p.fields[0].startswith(b'P1|'))
        fields = p.fields[0].split(b'|')
        assert len(fields) == 32 and fields[-1] == b'', 'P1 field count changed'
        assert all(re.fullmatch(rb'-?\d+', field) for field in fields[1:29])
        assert fields[28] == b'0', 'P1 reserved slot must be deterministic'
        assert fields[29] == NAME, 'P1 name position changed'
        return {name: int(fields[index]) for name, index in
                (('vi',5), ('str',6), ('tou',7), ('dx',8), ('lv',11), ('gld',21), ('bi',27))}

    def close(self):
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()


def saved_state():
    matches = []
    for path in Path('/run-test/saac/char').rglob('*'):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if raw.startswith(NAME+b'|'):
            matches.append((path, raw))
    if len(matches) != 1:
        return None
    path, raw = matches[0]
    # SAAC stores the escaped character document after name and option fields.
    expanded = raw.split(b'|', 2)[2].replace(b'\\n', b'\n')
    values = {}
    for field in (b'fl', b'x', b'y', b'dir', b'lv', b'gld', b'vi', b'str', b'tou', b'dx', b'pn', b'bi', b'fb'):
        match = re.search(rb'(?:^|\n)'+field+rb'=(-?\d+)(?:\n|$)', expanded)
        if not match:
            return None
        values[field.decode()] = int(match[1])
    return {'path': str(path.relative_to('/run-test')), 'sha256': hashlib.sha256(raw).hexdigest(), 'values': values}


def wait_saved(position, timeout=25):
    end = time.monotonic()+timeout
    while time.monotonic()<end:
        state = saved_state()
        if state and (state['values']['fl'], state['values']['x'], state['values']['y']) == (position['floor'], position['x'], position['y']):
            return state
        time.sleep(0.2)
    raise AssertionError(f'Saved position did not match {position}; last state {state}')


def run():
    assert not any(p.is_file() for p in Path('/run-test/saac/char').rglob('*')), 'Fixture character store must start empty'
    client = Client()
    client.reject_wrong_password()
    client.login()
    initial_list = client.charlist()
    assert NAME not in initial_list, initial_list
    record('empty_character_list', data=text(initial_list))
    client.send(73, [0, NAME, 100000, 30000, 3, 4, 6, 7, 10, 0, 0, 0, 0])
    created = client.wait(74)
    assert created.fields[0] == b'successful', created.fields
    record('character_created', reply=[text(x) for x in created.fields])
    listing = client.charlist()
    assert NAME in listing, listing
    record('character_listed', data=text(listing))
    start = client.enter()
    assert start['floor'] == 1006
    record('map_entered', **start)
    initial_player = client.player_state()
    record('player_status_received', **initial_player)
    requested_bounds = [start['floor'], max(0,start['x']-1), max(0,start['y']-1), start['x']+2, start['y']+2]
    client.send(38, requested_bounds)
    map_packet = client.wait(39)
    assert list(map_packet.fields[:5]) == requested_bounds, map_packet.fields[:5]
    map_sections = map_packet.fields[-1].split(b'|')
    assert len(map_sections) == 4, map_sections
    expected_tiles = (requested_bounds[3]-requested_bounds[1]) * (requested_bounds[4]-requested_bounds[2])
    assert all(len(section.split(b',')) == expected_tiles for section in map_sections[1:])
    assert all(tile for tile in map_sections[1].split(b','))
    record('map_data_received', bounds=list(map_packet.fields[:5]), payload_bytes=len(map_packet.fields[-1]))
    # Request one ordinary walk step and query authoritative server coordinates.
    moved = start
    for direction in b'abcdefgh':
        client.send(0, [moved['x'], moved['y'], bytes([direction])])
        time.sleep(0.5)
        moved = client.position()
        if (moved['x'], moved['y']) != (start['x'], start['y']):
            break
    assert moved['floor'] == start['floor'] and (moved['x'], moved['y']) != (start['x'], start['y']), moved
    assert max(abs(moved['x']-start['x']), abs(moved['y']-start['y'])) == 1
    record('movement_verified', before=start, after=moved, direction=chr(direction))
    saved = wait_saved(moved)
    record('autosave_verified_before_disconnect', **saved)
    client.close()
    time.sleep(1)
    reconnect = Client()
    reconnect.login()
    listing = reconnect.charlist()
    assert NAME in listing
    restored = reconnect.enter()
    assert restored == moved, (restored, moved)
    restored_player = reconnect.player_state()
    assert restored_player == initial_player, (restored_player, initial_player)
    persisted = wait_saved(restored)
    for key in ('vi', 'str', 'tou', 'dx'):
        assert restored_player[key] * 100 == persisted['values'][key]
    for key in ('lv', 'gld', 'bi'):
        assert restored_player[key] == persisted['values'][key]
    stable_fields = ('fl','x','y','dir','lv','gld','vi','str','tou','dx','pn','bi','fb')
    assert {k: saved['values'][k] for k in stable_fields} == {k: persisted['values'][k] for k in stable_fields}
    record('reconnect_persistence_verified', position=restored, player_status=restored_player, persisted_fields={k:persisted['values'][k] for k in stable_fields})
    # Also exercise normal protocol logout; this legacy action returns to elder spawn.
    reconnect.send(81, [])
    logout = reconnect.wait(82)
    assert logout.fields[0] == b'successful' and logout.fields[1] == b'success', logout.fields
    logout_save = wait_saved(start)
    record('explicit_logout_save_verified', reply=[text(x) for x in logout.fields], saved_position={k:logout_save['values'][k] for k in ('fl','x','y')})
    reconnect.close()
    return {'status': 'passed', 'events': EVENTS, 'scope': 'login-create-map-move-autosave-disconnect-reconnect-explicit-logout', 'fixture_account': text(ACCOUNT), 'known_limitations': ['P1 numeric slot 28 is reserved zero; its historical meaning is unverified.', 'Live-service reconnect only; process restart, crash durability, complete map correctness, battle and production security are not tested.']}


if __name__ == '__main__':
    try:
        result = run()
    except Exception as error:
        result = {'status': 'failed', 'events': EVENTS, 'error': str(error), 'traceback': traceback.format_exc()}
        (LOGS/'lifecycle-results.json').write_text(json.dumps(result, indent=2)+'\n')
        raise
    else:
        (LOGS/'lifecycle-results.json').write_text(json.dumps(result, indent=2)+'\n')
    finally:
        WIRE.close()
