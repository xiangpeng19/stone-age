#!/usr/bin/env python3
"""Loopback TCP to one fixed private Unix socket. No game-port forwarding."""
import argparse
import asyncio
from pathlib import Path
import signal


async def main(args):
    peers = set()
    tasks = set()
    async def handle(reader, writer):
        current = asyncio.current_task()
        tasks.add(current)
        if len(peers) >= 8:
            writer.close()
            tasks.discard(current)
            return
        peers.add(writer)
        target = None
        try:
            remote_reader, target = await asyncio.wait_for(asyncio.open_unix_connection(args.socket), 3)
            async def pump(source, destination):
                while True:
                    block = await source.read(16384)
                    if not block:
                        return
                    destination.write(block)
                    await destination.drain()
            first = asyncio.create_task(pump(reader, target))
            second = asyncio.create_task(pump(remote_reader, writer))
            done, pending = await asyncio.wait((first, second), return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(first, second, return_exceptions=True)
        except (OSError, asyncio.TimeoutError):
            pass
        finally:
            if target is not None:
                target.close()
            writer.close()
            peers.discard(writer)
            tasks.discard(current)
    server = await asyncio.start_server(handle, "127.0.0.1", args.port, limit=32768)
    stopped = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stopped.set)
    try:
        await stopped.wait()
    finally:
        server.close()
        await server.wait_closed()
        for writer in peers:
            writer.close()
        for task in tuple(tasks):
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--port", type=int, default=18680)
    asyncio.run(main(parser.parse_args()))
