#!/usr/bin/env python3
"""Exercise the real loopback gateway; store only asserted public test facts."""
import argparse
import asyncio
import json
from pathlib import Path

from aiohttp import ClientSession, WSServerHandshakeError


async def verify(args):
    base = f"http://127.0.0.1:{args.port}"
    events = []
    def record(name, **facts):
        event = {"test": name, "status": "passed", **facts}
        events.append(event)
        print(json.dumps(event), flush=True)

    async with ClientSession() as session:
        async with session.get(base+"/") as response:
            assert response.status == 200
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        async with session.get(base+"/", headers={"Host": "other.example"}) as response:
            assert response.status == 403
        for origin in (None, "http://other.example", "null"):
            try:
                ws = await session.ws_connect(base+"/ws", origin=origin)
            except WSServerHandshakeError as error:
                assert error.status == 403
            else:
                await ws.close()
                raise AssertionError("Untrusted WebSocket origin accepted")
        record("host_origin_and_csp")

        async def connect():
            ws = await session.ws_connect(base+"/ws", origin=base, max_msg_size=262144)
            assert (await ws.receive_json())["event"] == "ready"
            return ws

        next_id = 1
        async def rpc(ws, action, **extra):
            nonlocal next_id
            request_id, next_id = next_id, next_id+1
            await ws.send_json({"id": request_id, "action": action, **extra})
            response = await asyncio.wait_for(ws.receive_json(), 40)
            assert response["id"] == request_id
            return response

        ws = await connect()
        entered = await rpc(ws, "enter")
        assert entered["ok"] and entered["online"]
        map_data = entered["map"]
        assert map_data["bounds"] == [0, 0, 30, 40]
        assert all(len(map_data[layer]) == 1200 for layer in ("tiles", "objects", "events"))
        start = entered["position"]
        assert (start["floor"], start["x"], start["y"]) == (1006, 15, 22)
        await ws.send_json({"id": entered["id"], "action": "enter"})
        assert await ws.receive_json() == entered
        duplicate = await rpc(ws, "enter")
        assert duplicate["ok"] and duplicate["already_entered"]
        second = await connect()
        busy = await rpc(second, "enter")
        assert not busy["ok"] and busy["error"] == "demo_busy"
        await second.close()
        record("entry_map_duplicate_entry_and_second_controller", created=entered["created"], tiles=1200)

        for extra in ({"password": "x"*16}, {"account": "other"}, {"host": "other"}):
            invalid = await rpc(ws, "enter", **extra)
            assert not invalid["ok"] and invalid["error"] == "invalid_request"
        invalid = await rpc(ws, "move", direction="teleport")
        assert not invalid["ok"]
        current = await rpc(ws, "status")
        assert current["position"] == start
        record("invalid_identity_backend_and_movement_rejected")
        await asyncio.sleep(1.05)

        first_id, second_id = next_id, next_id+1
        next_id += 2
        await ws.send_json({"id": first_id, "action": "move", "direction": "north"})
        await ws.send_json({"id": second_id, "action": "move", "direction": "east"})
        replies = {}
        for _ in range(2):
            response = await asyncio.wait_for(ws.receive_json(), 15)
            replies[response["id"]] = response
        assert replies[first_id]["ok"]
        assert not replies[second_id]["ok"] and replies[second_id]["error"] == "busy"
        moved = replies[first_id]["position"]
        assert (moved["x"], moved["y"]) == (15, 21)
        await ws.send_json({"id": first_id, "action": "move", "direction": "north"})
        assert await ws.receive_json() == replies[first_id]
        current = await rpc(ws, "status")
        assert current["position"] == moved
        record("serialized_fast_input_and_idempotent_move", position=moved)

        blocked = None
        deltas = {"north": (0,-1), "west": (-1,0), "east": (1,0), "south": (0,1)}
        for direction in deltas:
            for _ in range(30):
                dx, dy = deltas[direction]
                nx, ny = moved["x"]+dx, moved["y"]+dy
                if not (0 <= nx < 30 and 0 <= ny < 40):
                    break
                index = ny*30+nx
                if map_data["events"][index]:
                    break  # Do not enter warp/event flows outside this demo's scope.
                response = await rpc(ws, "move", direction=direction)
                assert response["ok"]
                if response["blocked"]:
                    assert response["position"] == moved
                    blocked = {"target": [nx,ny], "tile": map_data["tiles"][index],
                               "object": map_data["objects"][index], "position": moved}
                    break
                moved = response["position"]
            if blocked:
                break
        assert blocked is not None, "No interior blocked destination was tested"
        record("interior_blocked_destination_authoritative", **blocked)

        saved = await rpc(ws, "save")
        assert saved["ok"] and saved["save_confirmed"]
        expected = {key: moved[key] for key in ("floor", "x", "y")}
        assert saved["saved"]["position"] == expected
        record("native_online_autosave_confirmed", position=expected)
        await ws.close()  # Abrupt browser transport loss: no native logout opcode.
        await asyncio.sleep(1.3)
        ws = await connect()
        restored = await rpc(ws, "enter")
        assert restored["ok"] and restored["position"] == moved
        record("websocket_disconnect_reconnect_persistence", position=expected)
        disconnected = await rpc(ws, "disconnect")
        assert disconnected["ok"] and not disconnected["online"]
        restored_again = await rpc(ws, "enter")
        assert restored_again["ok"] and restored_again["position"] == moved
        record("explicit_disconnect_action_reconnect")
        logout = await rpc(ws, "logout")
        assert logout["ok"] and logout["normal_logout"]
        assert logout["saved"]["position"] == {"floor": 1006, "x": 15, "y": 22}
        final = await rpc(ws, "enter")
        assert final["ok"] and (final["position"]["x"], final["position"]["y"]) == (15,22)
        await ws.close()
        await asyncio.sleep(1.3)
        record("normal_logout_saved_spawn_separate_from_disconnect")

        oversize = await connect()
        await oversize.send_str("x"*2048)
        await oversize.receive()
        assert oversize.close_code == 1009
        record("oversized_frame_rejected")
        rapid = await connect()
        for number in range(1, 21):
            await rapid.send_json({"id": number, "action": "status"})
        for _ in range(25):
            message = await asyncio.wait_for(rapid.receive(), 5)
            if rapid.closed:
                break
        assert rapid.close_code == 1008
        record("message_rate_limit_rejected")
    result = {"status": "passed", "events": events,
              "scope": "fixed-fixture web gateway; no battle, pets, production or restart validation"}
    args.output.write_text(json.dumps(result, indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18680)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(verify(parser.parse_args()))
