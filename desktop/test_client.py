"""Exercises the helper without a phone: pairs with the PIN, then moves, clicks, scrolls and types.

Open Notepad/TextEdit and put the mouse over it before running.
"""
import argparse
import asyncio
import json
import math

from websockets.asyncio.client import connect


async def run(args):
    async with connect(f"ws://{args.host}:{args.port}/") as ws:
        async def send(**msg):
            await ws.send(json.dumps(msg))

        await send(t="pair", pin=args.pin, device="test-client")
        reply = json.loads(await ws.recv())
        print("<-", reply)
        if reply.get("t") != "paired":
            return

        async def listen():
            async for raw in ws:
                print("<-", raw)

        listener = asyncio.create_task(listen())

        print("Drawing a circle with the cursor...")
        for i in range(120):
            a = i / 120 * 2 * math.pi
            await send(t="move", dx=-math.sin(a) * 4, dy=math.cos(a) * 4)
            await asyncio.sleep(1 / 120)

        print("Left click (focus the window under the cursor)")
        await send(t="click", button="left", count=1)
        await asyncio.sleep(0.5)

        print("Typing text")
        await send(t="text", s="Hello from Phone Trackpad! àèé ✓\nSecond line")
        await send(t="key", name="backspace", mods=[])
        await asyncio.sleep(0.5)

        print("Select all with cmd+a (Ctrl+A on Windows)")
        await send(t="key", name="a", mods=["cmd"])
        await send(t="key", name="right", mods=[])

        print("Scrolling")
        for _ in range(20):
            await send(t="scroll", dx=0, dy=0.25)
            await asyncio.sleep(0.02)

        await send(t="ping")
        await asyncio.sleep(1)
        listener.cancel()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pin")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
