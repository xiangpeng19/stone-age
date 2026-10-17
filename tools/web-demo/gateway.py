#!/usr/bin/env python3
"""Exact-origin, single-controller demo gateway over a private Unix socket."""
import argparse
import asyncio
from collections import OrderedDict, deque
import contextlib
import json
import logging
import os
from pathlib import Path
import time
import traceback

from aiohttp import web, WSMsgType
from native import NativeClient, DemoError, DIRECTIONS

HERE = Path(__file__).resolve().parent
SECURITY_HEADERS = {
    "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
}


def validate_request(data):
    if not isinstance(data, dict) or type(data.get("id")) is not int or not 1 <= data["id"] < 2**31:
        raise DemoError("invalid_request")
    action = data.get("action")
    if action not in ("enter", "move", "save", "disconnect", "logout", "status"):
        raise DemoError("invalid_action")
    allowed = {"id", "action", "direction"} if action == "move" else {"id", "action"}
    if set(data) != allowed:
        raise DemoError("invalid_fields")
    if action == "move" and data["direction"] not in DIRECTIONS:
        raise DemoError("invalid_direction")
    return data


class Gateway:
    def __init__(self, runtime, port, log):
        self.runtime, self.port, self.log = Path(runtime), port, Path(log)
        self.owner = None
        self.sessions = set()
        self.control_lock = asyncio.Lock()
        self.reconnect_after = 0.0

    def event(self, action, outcome):
        # Never serialize a received request, native packet, account or password.
        with self.log.open("a") as output:
            output.write(json.dumps({"time": time.time(), "action": action, "outcome": outcome})+"\n")

    async def websocket(self, request):
        expected = f"http://127.0.0.1:{self.port}"
        if request.headers.getall("Origin", []) != [expected]:
            raise web.HTTPForbidden(text="Origin rejected")
        if len(self.sessions) >= 4:
            raise web.HTTPServiceUnavailable(text="Demo session limit")
        ws = web.WebSocketResponse(max_msg_size=1024, heartbeat=15, compress=False)
        await ws.prepare(request)
        self.sessions.add(ws)
        client = None
        pending = None
        pending_id = None
        cache = OrderedDict()
        recent = deque()
        last_move = 0.0

        async def release():
            nonlocal client
            previous, client = client, None
            try:
                if previous is not None:
                    await previous.close()
            finally:
                if self.owner is ws:
                    self.owner = None
                    self.reconnect_after = time.monotonic()+0.8
                    self.event("release", "ok")

        async def execute(data):
            nonlocal client, last_move
            action, request_id = data["action"], data["id"]
            try:
                if action == "enter":
                    if client is not None:
                        result = {"online": True, "already_entered": True,
                                  "position": client.position.copy()}
                    else:
                        async with self.control_lock:
                            if self.owner is not None and self.owner is not ws:
                                raise DemoError("demo_busy")
                            self.owner = ws
                            client = NativeClient(self.runtime)
                        await asyncio.sleep(max(0, self.reconnect_after-time.monotonic()))
                        result = await client.enter()
                elif action == "status":
                    result = {"online": client is not None,
                              "position": await client.query_position() if client else None}
                elif action == "disconnect":
                    await release()
                    result = {"online": False, "disconnected": True}
                else:
                    if client is None:
                        raise DemoError("not_connected")
                    if action == "move":
                        now = time.monotonic()
                        if now-last_move < 0.25:
                            raise DemoError("rate_limited")
                        last_move = now
                        result = await client.move(data["direction"])
                    elif action == "save":
                        result = await client.confirm_save()
                    else:
                        result = await client.logout()
                        await release()
                response = {"id": request_id, "ok": True, "action": action, **result}
                self.event(action, "ok")
            except DemoError as error:
                code = str(error)
                if code not in ("demo_busy", "not_connected", "rate_limited"):
                    await release()
                response = {"id": request_id, "ok": False, "error": code, "online": client is not None}
                self.event(action, code)
            except (OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError):
                await release()
                response = {"id": request_id, "ok": False, "error": "native_connection_lost", "online": False}
                self.event(action, "native_connection_lost")
            except Exception:
                await release()
                response = {"id": request_id, "ok": False, "error": "internal_error", "online": False}
                self.event(action, "internal_error")
            cache[request_id] = response
            while len(cache) > 32:
                cache.popitem(last=False)
            if not ws.closed:
                await ws.send_json(response)

        try:
            await ws.send_json({"event": "ready", "fixture": "LifeFixture", "single_controller": True})
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    if message.type == WSMsgType.BINARY:
                        await ws.close(code=1003, message=b"Text JSON only")
                    continue
                now = time.monotonic()
                recent.append(now)
                while recent and recent[0] < now-1:
                    recent.popleft()
                if len(recent) > 12:
                    await ws.close(code=1008, message=b"Rate limit")
                    break
                request_id = None
                try:
                    candidate = json.loads(message.data)
                    if (isinstance(candidate, dict) and type(candidate.get("id")) is int
                            and 1 <= candidate["id"] < 2**31):
                        request_id = candidate["id"]
                    data = validate_request(candidate)
                    request_id = data["id"]
                    if request_id in cache:
                        await ws.send_json(cache[request_id])
                        continue
                    if pending is not None and not pending.done():
                        code = "request_pending" if request_id == pending_id else "busy"
                        await ws.send_json({"id": request_id, "ok": False, "error": code})
                        continue
                    pending_id = request_id
                    pending = asyncio.create_task(execute(data))
                except (json.JSONDecodeError, DemoError, TypeError):
                    await ws.send_json({"id": request_id, "ok": False, "error": "invalid_request"})
                    self.event("invalid", "rejected")
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pending
            try:
                await release()
            finally:
                self.sessions.discard(ws)
        return ws

    async def cleanup(self, app):
        for ws in tuple(self.sessions):
            await ws.close(code=1001, message=b"Demo stopping")


def create_app(gateway):
    @web.middleware
    async def boundary(request, handler):
        if request.headers.getall("Host", []) != [f"127.0.0.1:{gateway.port}"] or request.query_string:
            raise web.HTTPForbidden(text="Request boundary rejected")
        response = await handler(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    app = web.Application(middlewares=[boundary], client_max_size=1024)
    async def static(request):
        filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[request.path]
        content_type = {"index.html": "text/html", "app.js": "application/javascript",
                        "style.css": "text/css"}[filename]
        return web.Response(body=(HERE/"static"/filename).read_bytes(), content_type=content_type, charset="utf-8")
    for route in ("/", "/app.js", "/style.css"):
        app.router.add_get(route, static)
    app.router.add_get("/ws", gateway.websocket)
    async def health(request):
        return web.json_response({"ready": True, "scope": "isolated-public-fixture"})
    app.router.add_get("/health", health)
    app.on_cleanup.append(gateway.cleanup)
    return app


def make_runner(gateway):
    # Jammy aiohttp 3.8 forwards AppRunner kwargs to RequestHandler.
    # shutdown_timeout belongs to the site in this version.
    return web.AppRunner(create_app(gateway), access_log=None)


async def main(args):
    def diagnostic(error):
        frames = traceback.extract_tb(error.__traceback__) if error is not None else []
        print(json.dumps({"gateway_error_type": type(error).__name__,
                          "frames": [{"file": frame.filename, "line": frame.lineno,
                                      "function": frame.name} for frame in frames]}), flush=True)
    class SafeHandler(logging.Handler):
        def emit(self, record):
            diagnostic(record.exc_info[1] if record.exc_info else None)
    logger = logging.getLogger("aiohttp.server")
    logger.handlers = [SafeHandler()]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    asyncio.get_running_loop().set_exception_handler(lambda loop, context: diagnostic(context.get("exception")))
    path = Path(args.socket)
    if path.exists():
        raise SystemExit("Refusing to replace an existing socket")
    gateway = Gateway(args.runtime, args.port, args.log)
    runner = make_runner(gateway)
    await runner.setup()
    await web.UnixSite(runner, str(path), shutdown_timeout=5).start()
    os.chmod(path, 0o600)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--port", type=int, default=18680)
    asyncio.run(main(parser.parse_args()))
